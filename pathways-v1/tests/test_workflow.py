import csv
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app
from course import COURSE_VERSION, LESSONS

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.prior=app.DB_PATH; app.DB_PATH=Path(self.temp.name)/'test.sqlite3'
        app.init_db(seed=False)
        with app.connect() as db:
            self.pid=app.signup(db,{'name':'Demo Advocate','email':'demo@example.test','country':'Kenya','background':'A fictional researcher','demo_acknowledged':True})['person_id']

    def tearDown(self):
        app.DB_PATH=self.prior; self.temp.cleanup()

    def payload(self,index=0,key='one',correct=True):
        lesson=LESSONS[index]
        return {'person_id':self.pid,'lesson_id':lesson['id'],'course_version':COURSE_VERSION,
                'reflection':'An original sample reflection for this test.',
                'answers':{q['id']:q['correct'] if correct else (q['correct']+1)%3 for q in lesson['questions']},'event_key':key}

    def test_case_insensitive_signup_does_not_duplicate(self):
        with app.connect() as db:
            with self.assertRaises(app.Invalid) as ctx:
                app.signup(db,{'name':'Other Demo','email':'DEMO@EXAMPLE.TEST','country':'Kenya','background':'Sample','demo_acknowledged':True})
            self.assertEqual(ctx.exception.status,409)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0],1)

    def test_replay_and_changed_event_identifier(self):
        with app.connect() as db:
            first=app.submit(db,self.payload()); again=app.submit(db,self.payload())
            self.assertEqual(first['submission_id'],again['submission_id']); self.assertTrue(again['replayed'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],1)
            changed=self.payload(); changed['reflection']='Different answers cannot reuse an event identifier.'
            with self.assertRaises(app.Invalid) as ctx: app.submit(db,changed)
            self.assertEqual(ctx.exception.status,409)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],1)

    def test_every_attempt_survives_and_latest_score_is_reported(self):
        with app.connect() as db:
            self.assertEqual(app.submit(db,self.payload(key='old',correct=False))['score'],0)
            latest=app.submit(db,self.payload(key='new',correct=True))
            self.assertEqual(latest['attempt'],2)
        with app.connect() as db:
            s=app.state(db); p=s['people'][0]
            self.assertEqual(len(s['submissions']),2);self.assertEqual(p['completed_sections'],1)
            self.assertEqual(p['score'],2);self.assertEqual(p['latest_submissions']['orientation']['attempt'],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM answers').fetchone()[0],4)

    def test_missing_answers_and_stale_version_are_rejected(self):
        for change in [{'answers':{}},{'course_version':'old-version'},{'reflection':'x'}]:
            with app.connect() as db:
                with self.assertRaises(app.Invalid):app.submit(db,{**self.payload(),**change})
                self.assertEqual(db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0],0)

    def test_completion_is_not_an_admission_score_gate(self):
        with app.connect() as db:
            for i in range(6): result=app.submit(db,self.payload(i,str(i),False))
            self.assertTrue(result['complete'])
            self.assertEqual(app.state(db)['people'][0]['score'],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages WHERE rule='completion'").fetchone()[0],1)
            app.submit(db,self.payload(5,'retake',False))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages WHERE rule='completion'").fetchone()[0],1)

    def make_inactive(self):
        old=(datetime.now(timezone.utc)-timedelta(days=10)).isoformat(timespec='seconds')
        with app.connect() as db:db.execute('UPDATE people SET last_active=? WHERE id=?',(old,self.pid))

    def test_reminders_deduplicate_and_return_suppresses_stale_messages(self):
        self.make_inactive()
        with app.connect() as db:
            self.assertEqual(app.run_followups(db)['queued'],1)
            self.assertEqual(app.run_followups(db)['queued'],0)
            app.submit(db,self.payload())
            self.assertEqual(db.execute("SELECT state FROM messages WHERE rule='inactivity'").fetchone()[0],'suppressed')

    def test_paused_messages_cannot_be_reviewed_or_requeued(self):
        self.make_inactive()
        with app.connect() as db:
            app.run_followups(db)
            mid=db.execute("SELECT id FROM messages WHERE rule='inactivity'").fetchone()[0]
            app.update_person(db,self.pid,{'messages_paused':True})
            self.assertEqual(app.run_followups(db)['queued'],0)
            with self.assertRaises(app.Invalid):app.review_message(db,mid)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages WHERE state!='suppressed'").fetchone()[0],0)

    def test_review_is_held_and_notes_and_owner_persist(self):
        with app.connect() as db:
            mid=db.execute('SELECT id FROM messages').fetchone()[0]
            result=app.review_message(db,mid)
            self.assertFalse(result['sent']);self.assertEqual(result['state'],'reviewed')
            app.update_person(db,self.pid,{'owner':'Jenna','stage':'Follow-up','next_action':'Discuss sample interests'})
        with app.connect() as db:self.assertEqual(app.person(db,self.pid)['owner'],'Jenna')

    def test_csv_is_safe_for_spreadsheet_opening(self):
        with app.connect() as db:app.update_person(db,self.pid,{'next_action':'=1+2'})
        with app.connect() as db:
            exported=list(csv.DictReader(io.StringIO(app.csv_bytes(db,'people').decode('utf-8-sig'))))
            self.assertEqual(exported[0]['next_action'],"'=1+2")

    def test_backup_restores_linked_records_and_history(self):
        with app.connect() as db:app.submit(db,self.payload())
        with app.connect() as db:bundle=app.backup_bytes(db)
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            self.assertIn('answers.csv',z.namelist());self.assertIn('course.json',z.namelist())
            restored=Path(self.temp.name)/'restored.sqlite3';restored.write_bytes(z.read('pathways.sqlite3'))
        with sqlite3.connect(restored) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM submissions s JOIN people p ON s.person_id=p.id').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM answers a JOIN submissions s ON a.submission_id=s.id').fetchone()[0],2)

    def test_http_signup_submission_state_and_cross_origin_rejection(self):
        http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        def request(path,payload=None,origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
            with urllib.request.urlopen(req) as r:return json.load(r)
        try:
            self.assertTrue(request('/api/health')['ok'])
            result=request('/api/submissions',self.payload())
            self.assertEqual(result['completed_sections'],1)
            self.assertEqual(request('/api/state')['people'][0]['completed_sections'],1)
            with self.assertRaises(urllib.error.HTTPError) as ctx:request('/api/followups/run',{},'https://unrelated.example')
            self.assertEqual(ctx.exception.code,403)
        finally:http.shutdown();http.server_close();thread.join()

    def test_seeding_does_not_repeat_after_restart(self):
        with app.connect() as db:app.seed_demo(db);db.execute("INSERT INTO settings VALUES ('seeded','1')")
        app.init_db()
        with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0],9)

if __name__=='__main__':unittest.main(verbosity=2)
