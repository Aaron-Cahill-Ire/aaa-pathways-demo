"""Loopback-only staff dashboard with synthetic Airtable and Thinkific adapters.

The retained learner preview uses transactional SQLite. Preview navigation is
not authentication. The dashboard makes server-side demo API calls; no emails
or model calls are made.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
from course import COURSE_VERSION, LESSONS, public_course
import integrations
import pipeline

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('PATHWAYS_DB', ROOT / 'data' / 'pathways.sqlite3'))
WRITE_LOCK = threading.RLock()

class Invalid(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex[:12]

def connect():
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db

def rows(db, sql, params=()):
    return [dict(r) for r in db.execute(sql, params).fetchall()]

def text(data, key, limit=200, required=True):
    value = data.get(key, '')
    if not isinstance(value, str): raise Invalid(f'{key} must be text.')
    value = value.strip()
    if required and not value: raise Invalid(f'Please provide {key.replace("_", " ")}.')
    if len(value) > limit: raise Invalid(f'{key} is too long (maximum {limit} characters).')
    return value

def person(db, person_id):
    row = db.execute('SELECT * FROM people WHERE id=?', (person_id,)).fetchone()
    if not row: raise Invalid('Participant not found.', 404)
    return dict(row)

def record(db, person_id, kind, detail, when=None):
    db.execute('INSERT INTO activity VALUES (?,?,?,?,?)', (uid('act'), person_id, kind, detail, when or now()))

def init_db(seed=True):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS people (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
          country TEXT NOT NULL, background TEXT NOT NULL, owner TEXT NOT NULL DEFAULT 'Unassigned',
          next_action TEXT NOT NULL DEFAULT 'Welcome and review background',
          programme TEXT NOT NULL DEFAULT 'Pathways', stage TEXT NOT NULL DEFAULT 'Learning',
          messages_paused INTEGER NOT NULL DEFAULT 0 CHECK(messages_paused IN (0,1)),
          marketing_opt_in INTEGER NOT NULL DEFAULT 0 CHECK(marketing_opt_in IN (0,1)),
          created_at TEXT NOT NULL, last_active TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS enrolments (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id),
          course_version TEXT NOT NULL, joined_at TEXT NOT NULL, completed_at TEXT,
          UNIQUE(person_id,course_version));
        CREATE TABLE IF NOT EXISTS submissions (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id),
          lesson_id TEXT NOT NULL, course_version TEXT NOT NULL, item_version TEXT NOT NULL,
          reflection TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 2),
          attempt INTEGER NOT NULL, submitted_at TEXT NOT NULL,
          UNIQUE(person_id,lesson_id,course_version,attempt));
        CREATE TABLE IF NOT EXISTS answers (
          id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id),
          item_code TEXT NOT NULL, answer INTEGER NOT NULL, score INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          event_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, source TEXT NOT NULL,
          person_id TEXT NOT NULL REFERENCES people(id), result_json TEXT NOT NULL,
          received_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id), rule TEXT NOT NULL,
          dedupe_key TEXT NOT NULL UNIQUE, subject TEXT NOT NULL, body TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('pending','reviewed','suppressed')),
          created_at TEXT NOT NULL, reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS notes (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id),
          body TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activity (
          id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id),
          kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_submissions_person ON submissions(person_id,submitted_at);
        CREATE INDEX IF NOT EXISTS ix_activity_person ON activity(person_id,created_at);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        if seed and not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            seed_demo(db)
            db.execute("INSERT INTO settings VALUES ('seeded','1')")

def signup(db, data):
    name = text(data, 'name', 100)
    email = text(data, 'email', 200).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email): raise Invalid('Enter a valid email address.')
    country = text(data, 'country', 80)
    background = text(data, 'background', 800)
    if data.get('demo_acknowledged') is not True: raise Invalid('Confirm that you are using fictional details in this preview.')
    if db.execute('SELECT 1 FROM people WHERE email=?', (email,)).fetchone():
        raise Invalid('This email already has a demo record. Open it from the participant list instead.', 409)
    for k in ['marketing_opt_in']:
        if k in data and type(data[k]) is not bool: raise Invalid(f'{k} must be true or false.')
    pid=uid('adv'); stamp=now()
    db.execute('INSERT INTO people (id,name,email,country,background,marketing_opt_in,created_at,last_active) VALUES (?,?,?,?,?,?,?,?)',
               (pid,name,email,country,background,int(data.get('marketing_opt_in',False)),stamp,stamp))
    db.execute('INSERT INTO enrolments VALUES (?,?,?,?,NULL)',(uid('enr'),pid,COURSE_VERSION,stamp))
    record(db,pid,'Joined','Joined the Pathways sample course. Programme messages only unless separately opted into marketing.')
    queue_message(db,pid,'welcome',f'welcome:{pid}', 'Your Pathways starting point',f'Hello {name.split()[0]},\n\nYour sample course is ready. Begin with orientation and return whenever you are ready.\n\nThis is a preview message. Nothing has been sent.')
    return {'person_id':pid}

def queue_message(db,pid,rule,key,subject,body):
    p=person(db,pid)
    state='suppressed' if p['messages_paused'] else 'pending'
    cur=db.execute('INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?,?,?,NULL)',(uid('msg'),pid,rule,key,subject,body,state,now()))
    return cur.rowcount

def submit(db,data,source='course-preview'):
    pid=text(data,'person_id',80); person(db,pid)
    lesson_id=text(data,'lesson_id',80)
    lesson=next((l for l in LESSONS if l['id']==lesson_id),None)
    if not lesson: raise Invalid('Unknown course section.')
    version=text(data,'course_version',80)
    if version!=COURSE_VERSION: raise Invalid('The course changed. Reload before submitting.',409)
    reflection=text(data,'reflection',3000)
    if len(reflection)<10: raise Invalid('Add a reflection of at least 10 characters.')
    answers=data.get('answers')
    if not isinstance(answers,dict) or set(answers)!=set(q['id'] for q in lesson['questions']): raise Invalid('Answer both knowledge checks.')
    for q in lesson['questions']:
        a=answers[q['id']]
        if type(a) is not int or not 0<=a<len(q['options']): raise Invalid('Choose one of the available answers.')
    event_key=text(data,'event_key',180)
    canonical=json.dumps({k:data[k] for k in ['person_id','lesson_id','course_version','reflection','answers']},sort_keys=True)
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    # Namespace external identifiers by source to avoid collisions between providers.
    key=f'{source}:{event_key}'
    prior=db.execute('SELECT * FROM events WHERE event_key=?',(key,)).fetchone()
    if prior:
        if prior['payload_hash']!=digest: raise Invalid('This event ID was already used with different answers. Use a new revision ID.',409)
        return {**json.loads(prior['result_json']),'replayed':True}
    attempt=db.execute('SELECT COUNT(*) FROM submissions WHERE person_id=? AND lesson_id=? AND course_version=?',(pid,lesson_id,version)).fetchone()[0]+1
    sid=uid('sub'); score=sum(answers[q['id']]==q['correct'] for q in lesson['questions']); stamp=now()
    db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?)',(sid,pid,lesson_id,version,'sample-rubric-1',reflection,score,attempt,stamp))
    for q in lesson['questions']:
        db.execute('INSERT INTO answers VALUES (?,?,?,?,?)',(uid('ans'),sid,q['id'],answers[q['id']],int(answers[q['id']]==q['correct'])))
    db.execute('UPDATE people SET last_active=? WHERE id=?',(stamp,pid))
    record(db,pid,'Assessment saved',f'{lesson["topic"]} · attempt {attempt} · {score}/2 knowledge checks. Source: {source}.')
    completed=db.execute('SELECT COUNT(DISTINCT lesson_id) FROM submissions WHERE person_id=? AND course_version=?',(pid,version)).fetchone()[0]
    # Completing means submitting all sample sections; quiz score is never an access gate.
    if completed==len(LESSONS):
        db.execute('UPDATE enrolments SET completed_at=COALESCE(completed_at,?) WHERE person_id=? AND course_version=?',(stamp,pid,version))
        db.execute("UPDATE people SET next_action=CASE WHEN next_action='Welcome and review background' THEN 'Review next-step preferences' ELSE next_action END WHERE id=?",(pid,))
        queue_message(db,pid,'completion',f'completion:{pid}:{version}','You completed the Pathways sample',f'Hello {person(db,pid)["name"].split()[0]},\n\nYou have saved all six sample exercises. Keep your action plan and choose a date to review it. This preview does not issue an official AAA certificate or promise programme access.\n\nNothing has been sent.')
    # Any successful return invalidates old inactivity messages.
    db.execute("UPDATE messages SET state='suppressed' WHERE person_id=? AND rule='inactivity' AND state IN ('pending','reviewed')",(pid,))
    result={'submission_id':sid,'score':score,'maximum':2,'attempt':attempt,'completed_sections':completed,'complete':completed==len(LESSONS),'replayed':False}
    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(key,digest,source,pid,json.dumps(result),stamp))
    return result

def run_followups(db):
    made=0; stamp=now(); cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat(timespec='seconds')
    for p in rows(db,'''SELECT p.*, e.completed_at FROM people p JOIN enrolments e ON e.person_id=p.id
                        WHERE e.course_version=?''',(COURSE_VERSION,)):
        if p['messages_paused'] or p['completed_at'] or p['last_active']>cutoff:
            db.execute("UPDATE messages SET state='suppressed' WHERE person_id=? AND rule='inactivity' AND state IN ('pending','reviewed')",(p['id'],))
            continue
        made+=queue_message(db,p['id'],'inactivity',f'inactivity:{p["id"]}:{p["last_active"]}',
                 'Continue where you left off',f'Hello {p["name"].split()[0]},\n\nYour Pathways sample exercises are saved. Return to your next section whenever it fits your schedule. If you would like help, your programme contact can assist.\n\nPreview only. Nothing has been sent.')
    db.execute("INSERT INTO settings VALUES ('last_reminder_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(stamp,))
    return {'queued':made,'sent':0,'checked_at':stamp}

def state(db):
    people=rows(db,'''SELECT p.*,e.completed_at FROM people p JOIN enrolments e ON e.person_id=p.id WHERE e.course_version=? ORDER BY p.created_at DESC,p.name''',(COURSE_VERSION,))
    submissions=rows(db,'SELECT * FROM submissions ORDER BY submitted_at DESC,rowid DESC')
    for p in people:
        own=[s for s in submissions if s['person_id']==p['id'] and s['course_version']==COURSE_VERSION]
        latest={}
        for s in own: latest.setdefault(s['lesson_id'],s)
        p['completed_sections']=len(latest); p['score']=sum(s['score'] for s in latest.values()); p['maximum']=len(latest)*2
        p['status']='Completed' if p['completed_at'] else 'Needs a nudge' if p['last_active']<(datetime.now(timezone.utc)-timedelta(days=7)).isoformat() else 'Learning' if latest else 'Just joined'
        p['latest_submissions']=latest
    return {'people':people,'submissions':submissions,'messages':rows(db,'''SELECT m.*,p.name,p.email FROM messages m JOIN people p ON p.id=m.person_id ORDER BY m.created_at DESC,m.rowid DESC'''),
            'notes':rows(db,'SELECT * FROM notes ORDER BY created_at DESC,rowid DESC'),
            'activity':rows(db,'''SELECT a.*,p.name FROM activity a JOIN people p ON a.person_id=p.id ORDER BY a.created_at DESC,a.rowid DESC LIMIT 200'''),
            'course':public_course(),'settings':{r['key']:r['value'] for r in db.execute('SELECT * FROM settings')},'local_only':True}

def update_person(db,pid,data):
    person(db,pid)
    allowed={'owner','next_action','programme','stage','messages_paused'}
    if not data or set(data)-allowed: raise Invalid('Unsupported participant update.')
    for k,v in data.items():
        if k=='messages_paused':
            if type(v) is not bool: raise Invalid('messages_paused must be true or false.')
            v=int(v)
        else:
            if not isinstance(v,str) or not v.strip() or len(v)>300: raise Invalid(f'Invalid {k}.')
            v=v.strip()
        if k=='stage' and v not in ['Learning','Follow-up','Application','Interview','Programme','Alumni']: raise Invalid('Unknown programme stage.')
        db.execute(f'UPDATE people SET {k}=? WHERE id=?',(v,pid))
    if data.get('messages_paused'):
        db.execute("UPDATE messages SET state='suppressed' WHERE person_id=? AND state IN ('pending','reviewed')",(pid,))
    record(db,pid,'Record updated','; '.join(f'{k.replace("_"," ")}: {v}' for k,v in data.items()))
    return {'updated':True}

def review_message(db,mid):
    m=db.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone()
    if not m: raise Invalid('Message not found.',404)
    p=person(db,m['person_id'])
    e=db.execute('SELECT completed_at FROM enrolments WHERE person_id=? AND course_version=?',(p['id'],COURSE_VERSION)).fetchone()
    if m['state']!='pending': raise Invalid('This message is no longer waiting for review.',409)
    if p['messages_paused'] or (m['rule']=='inactivity' and (e['completed_at'] or p['last_active']>(datetime.now(timezone.utc)-timedelta(days=7)).isoformat())):
        db.execute("UPDATE messages SET state='suppressed' WHERE id=?",(mid,))
        return {'state':'suppressed','sent':False}
    db.execute("UPDATE messages SET state='reviewed',reviewed_at=? WHERE id=?",(now(),mid))
    record(db,p['id'],'Message reviewed',f'{m["subject"]} · held locally; not sent.')
    return {'state':'reviewed','sent':False}

TABLES=['people','enrolments','submissions','answers','events','messages','notes','activity']

def csv_bytes(db,name):
    if name not in TABLES: raise Invalid('Unknown export.',404)
    cur=db.execute(f'SELECT * FROM {name}'); output=io.StringIO(newline=''); writer=csv.writer(output)
    writer.writerow([c[0] for c in cur.description])
    for row in cur:
        # Protect CSV consumers from spreadsheet formula injection.
        writer.writerow(["'"+str(v) if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
    return output.getvalue().encode('utf-8-sig')

def backup_bytes(db):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for table in TABLES: z.writestr(table+'.csv',csv_bytes(db,table))
        z.writestr('course.json',json.dumps({'version':COURSE_VERSION,'lessons':LESSONS},indent=2))
        z.writestr('README.txt','Fictional-data preview export. IDs link the CSV tables. This portable export is not a tested production restore. Use the SQLite snapshot for local restoration.')
        # SQLite backup API provides a consistent, WAL-aware snapshot.
        snapshot=sqlite3.connect(':memory:'); db.backup(snapshot)
        z.writestr('pathways.sqlite3',snapshot.serialize()); snapshot.close()
    return output.getvalue()

def seed_demo(db):
    fixtures=[('Amina Okafor','Nigeria','Communications and community organising',4,1,'Stuart','Discuss policy research interests','Follow-up'),
              ('Kwame Mensah','Ghana','Operations and project coordination',6,2,'Stuart','Review next-step preferences','Follow-up'),
              ('Zuri Wanjiku','Kenya','Public health and research',2,11,'Jenna','Offer help with the next exercise','Learning'),
              ('Thabo Mokoena','South Africa','Supply chain and business',3,3,'Stuart','Review career comparison','Learning'),
              ('Nadia Hassan','Egypt','Law and policy',1,9,'Jenna','Check whether support is needed','Learning'),
              ('Jean Niyonzima','Rwanda','Data analysis and programme evaluation',5,1,'Stuart','Review the draft action plan','Learning'),
              ('Abena Owusu','Ghana','Education and facilitation',6,4,'Jenna','Record programme follow-up','Programme'),
              ('Samuel Adeyemi','Nigeria','Veterinary studies',0,1,'Unassigned','Send a welcome and point to orientation','Learning')]
    for idx,(name,country,background,count,days,owner,next_action,stage) in enumerate(fixtures):
        joined=(datetime.now(timezone.utc)-timedelta(days=20+idx)).isoformat(timespec='seconds')
        result=signup(db,{'name':name,'email':name.lower().replace(' ','.')+'@example.test','country':country,'background':background,'demo_acknowledged':True})
        pid=result['person_id']
        for li,l in enumerate(LESSONS[:count]):
            answers={q['id']:q['correct'] for q in l['questions']}
            if (idx+li)%3==0: answers[l['questions'][0]['id']]=(answers[l['questions'][0]['id']]+1)%3
            submit(db,{'person_id':pid,'lesson_id':l['id'],'course_version':COURSE_VERSION,'reflection':f'Sample reflection: I want to explore how my experience in {background.lower()} could contribute. My next step is to speak with someone doing this work.','answers':answers,'event_key':f'seed-{idx}-{li}'})
        last=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
        db.execute('UPDATE people SET owner=?, next_action=?, stage=?, created_at=?,last_active=? WHERE id=?',(owner,next_action,stage,joined,last,pid))
        db.execute('UPDATE enrolments SET joined_at=? WHERE person_id=?',(joined,pid))
        db.execute("UPDATE messages SET state='reviewed',reviewed_at=? WHERE person_id=? AND rule='welcome'",(joined,pid))
    run_followups(db)

class Handler(BaseHTTPRequestHandler):
    server_version='PathwaysLocalV1'

    def send(self,status,payload,ctype='application/json; charset=utf-8',filename=None):
        body=json.dumps(payload).encode() if isinstance(payload,(dict,list)) else payload
        self.send_response(status)
        self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        script_policy="'self'"
        if urlparse(self.path).path=='/handoff/review.html' and ctype.startswith('text/html'):
            match=re.search(rb'<script type="module">(.*?)</script>',body,re.S)
            if match: script_policy+=" 'sha256-"+base64.b64encode(hashlib.sha256(match.group(1)).digest()).decode()+"'"
        self.send_header('Content-Security-Policy',f"default-src 'self'; script-src {script_policy}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)

    def guard(self,mutation=False):
        expected=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') not in [expected,f'localhost:{self.server.server_port}']:
            raise Invalid('This fictional-data preview only accepts local requests.',403)
        origin=self.headers.get('Origin')
        if origin and origin not in [f'http://{expected}',f'http://localhost:{self.server.server_port}']:
            raise Invalid('Cross-origin requests are not allowed.',403)
        if mutation and self.headers.get('Content-Type','').split(';')[0]!='application/json':
            raise Invalid('Use application/json.',415)

    def do_GET(self):
        try:
            self.guard(); parsed=urlparse(self.path); path=unquote(parsed.path)
            if path=='/handoff/review.html':
                return self.send(200,(ROOT.parent/'handoff'/'AAA Dashboard Review.html').read_bytes(),'text/html; charset=utf-8')
            if path=='/api/health': return self.send(200,{'ok':True,'local_only':True})
            if path=='/api/dashboard': return self.send(200,integrations.snapshot())
            if path=='/api/dashboard/export': return self.send(200,integrations.export_csv(),'text/csv; charset=utf-8','aaa-demo-advocates.csv')
            downloads={'/handoff/contractor.docx':'AAA Dashboard Contractor Handoff.docx','/handoff/decisions.docx':'AAA Dashboard Decisions for AAA.docx','/handoff/AAA Dashboard Contractor Handoff.docx':'AAA Dashboard Contractor Handoff.docx','/handoff/AAA Dashboard Decisions for AAA.docx':'AAA Dashboard Decisions for AAA.docx'}
            if path in downloads:
                filename=ROOT.parent/'handoff'/downloads[path]
                if not filename.exists(): raise Invalid('Document is being prepared.',404)
                return self.send(200,filename.read_bytes(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename.name)
            if path=='/api/state':
                with connect() as db: return self.send(200,state(db))
            if path=='/api/export':
                name=parse_qs(parsed.query).get('table',['people'])[0]
                with connect() as db: return self.send(200,csv_bytes(db,name),'text/csv; charset=utf-8',f'pathways-{name}.csv')
            if path=='/api/backup':
                with connect() as db: body=backup_bytes(db)
                return self.send(200,body,'application/zip','pathways-demo-backup.zip')
            files={'/':'index.html','/learner':'learner.html','/app.js':'app.js','/style.css':'style.css','/dashboard.js':'dashboard.js','/dashboard.css':'dashboard.css'}
            if path not in files: raise Invalid('Page not found.',404)
            filename=ROOT/'static'/files[path]
            return self.send(200,filename.read_bytes(),{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[filename.suffix[1:]])
        except Invalid as e: self.send(e.status,{'error':e.message})
        except Exception as e:
            print(f'GET failed: {type(e).__name__}',flush=True); self.send(500,{'error':'The local request failed. Check the server terminal.'})

    def do_POST(self):
        try:
            self.guard(True)
            try: length=int(self.headers.get('Content-Length','0'))
            except ValueError: raise Invalid('Invalid content length.')
            if not 0<length<=50000: raise Invalid('The request is empty or too large.',413)
            try: data=json.loads(self.rfile.read(length))
            except (ValueError,UnicodeDecodeError): raise Invalid('Invalid JSON.')
            if not isinstance(data,dict): raise Invalid('Expected an object.')
            path=urlparse(self.path).path
            if re.fullmatch(r'/api/dashboard/assessments/rec[a-zA-Z0-9]+',path):
                return self.send(200,pipeline.submit_attempt(path.rsplit('/',1)[1],data))
            if path=='/api/dashboard/refresh': return self.send(200,integrations.sync())
            if re.fullmatch(r'/api/dashboard/records/rec[a-zA-Z0-9]+',path):
                return self.send(200,integrations.update_demo(path.rsplit('/',1)[1],data))
            with WRITE_LOCK, connect() as db:
                if path=='/api/signup': result=signup(db,data)
                elif path=='/api/submissions': result=submit(db,data)
                elif path=='/api/followups/run': result=run_followups(db)
                elif re.fullmatch(r'/api/people/adv_[a-f0-9]{12}',path): result=update_person(db,path.rsplit('/',1)[1],data)
                elif re.fullmatch(r'/api/notes/adv_[a-f0-9]{12}',path):
                    pid=path.rsplit('/',1)[1]; person(db,pid); body=text(data,'body',3000)
                    db.execute('INSERT INTO notes VALUES (?,?,?,?)',(uid('note'),pid,body,now())); record(db,pid,'Staff note added',body); result={'saved':True}
                elif re.fullmatch(r'/api/messages/msg_[a-f0-9]{12}/review',path): result=review_message(db,path.split('/')[3])
                else: raise Invalid('Endpoint not found.',404)
            self.send(200,result)
        except (Invalid,integrations.IntegrationError) as e: self.send(e.status,{'error':e.message})
        except Exception as e:
            print(f'POST failed: {type(e).__name__}',flush=True); self.send(500,{'error':'The change was not saved. Check the server terminal.'})

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); args=parser.parse_args()
    init_db()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'AAA dashboard running at http://127.0.0.1:{args.port}\nSynthetic Airtable records only. Thinkific demo reads. No email sending.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
