"""Opt-in live acceptance. Creates one idempotent, explicitly fictional attempt.
Run from pathways-v1: python3 tests/live_demo_check.py --fictional-demo-only
Never publishes a course, sends email or touches non-demo records.
"""
import argparse
import json
import sys
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import integrations as a
import pipeline as p
import server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fictional-demo-only',action='store_true',required=True);parser.parse_args()
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{http.server_port}'
    def api(path,body=None):
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Origin':url})
        with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
    try:
        payload={'q1':'A','q2':'B','reflection':'Fictional HTTP integration check for Amina. Repeat delivery must not create another attempt.','event_key':'aaa-live-http-amina-20261023'}
        path='/api/dashboard/assessments/recUwfcioI2FWLpFW'
        first=api(path,payload);second=api(path,payload);assert first['source_key']==second['source_key'];assert second['replayed']
        try:api(path,{**payload,'q2':'A'});raise AssertionError('Changed replay accepted')
        except urllib.error.HTTPError as e:assert e.code==409
        state=api('/api/dashboard');attempts=state['assessments']['attempts']
        nuru=[x for x in attempts if x['advocate_id']=='recGeNBArbf48utG1'];assert [x['score'] for x in nuru]==[0,2]
        assert all(x['mirrored_id'] for x in attempts)
        assert {'unmatched','conflict'}<=set(x['match_state'] for x in state['assessments']['review'])
        assert len(state['people'])==6;assert len(state['thinkific_data']['enrollments'])==2
        for person in state['people'][:2]:
            assert person['percent']==0 and person['completed'] is None and person['thinkific']['started_at'] is None
        assert state['thinkific_data']['native_quizzes']['state']=='verified'
        c=a.airtable_config();source,target=p.table_ids(c);remote=p.records(c,target);assert len(remote)==len(attempts)
        # Reconstruct from remote envelopes into an isolated new database, without discarding the live journal.
        original_db=p.DB
        with tempfile.TemporaryDirectory() as folder:
            p.DB=Path(folder)/'restored.sqlite3'
            try:
                p.restore_attempts(c,target);restored=p.assessment_state();assert len(restored['attempts'])==len(attempts)
                assert [x['score'] for x in restored['attempts'] if x['advocate_id']=='recGeNBArbf48utG1']==[0,2]
            finally:p.DB=original_db
        evidence={'verified_at':a.stamp(),'connections':{k:state[k] for k in ['airtable','thinkific','assessment_connection']},'enrollments':state['thinkific_data']['enrollments'],'native_quizzes':state['thinkific_data']['native_quizzes'],'assessment_attempts':attempts,'review':state['assessments']['review'],'http_replay':{'source_key':first['source_key'],'replayed':second['replayed'],'changed_payload_status':409},'replay_counts':{'local_attempts':len(attempts),'remote_attempts':len(remote),'pending_mirrors':0},'remote_restore_verified':True,'limitation':'Course remains unpublished. No enrolled-learner lesson activity or stored quiz attempt verified; publication approval is required for that acceptance step.'}
        (a.ROOT.parent/'thinkific-demo/live_integration_evidence.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps({k:v for k,v in evidence.items() if k not in ['enrollments','assessment_attempts','review']},indent=2))
    finally:http.shutdown();http.server_close()
