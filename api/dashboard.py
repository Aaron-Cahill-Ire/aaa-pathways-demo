"""Read-only hosted adapter. Live credentials stay in Vercel environment variables.

Never calls sync(), persist_progress(), mirror(), or any vendor write endpoint.
The local integration remains the place for staff changes and ingestion writes.
"""
import copy
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pathways-v1'))
import integrations as sources
import pipeline

LOCK = threading.RLock()
CACHE = None
CACHE_AT = 0
REQUIRED = ('AIRTABLE_TOKEN', 'AIRTABLE_BASE_ID', 'THINKIFIC_API_TOKEN')

def baseline():
    value = json.loads((ROOT / 'web-demo/data/snapshot.json').read_text())
    value.update(hosted_demo=True, hosted_mode='snapshot', read_only=True, local_only=False)
    return value

def read_live():
    """Read pinned fictional profiles, enrolments and assessment source rows."""
    people, table, base = sources.pull_airtable()
    registered = {p['id']: p for p in pipeline.registry()['advocates']}
    if len(people) != 6 or {p['id'] for p in people} != set(registered):
        raise sources.IntegrationError('The six registered fictional advocates could not be verified.')
    for person in people:
        if any(person[k] != registered[person['id']][k] for k in ('demo_id','name','email')):
            raise sources.IntegrationError('A registered fictional identity changed. Live refresh stopped.')
    thinkific = sources.pull_thinkific(people)
    enrollment = {e['advocate_id']:e for e in thinkific['enrollments']}
    for person in people:
        if person['id'] in enrollment:
            event = enrollment[person['id']]
            person.update(thinkific=event, percent=event['percent'], completed=None,
                          progress_source='Verified Thinkific API')
        else:
            person.update(thinkific=None, progress_source='Synthetic seed')
    # SQLite is scratch space only. Every refresh rebuilds it from Airtable;
    # no state depends on a warm function instance or a persistent local disk.
    with tempfile.TemporaryDirectory(prefix='aaa-readonly-') as temp:
        previous = pipeline.DB
        pipeline.DB = Path(temp) / 'attempts.sqlite3'
        try:
            config = sources.airtable_config()
            source, target = pipeline.table_ids(config)
            pipeline.restore_attempts(config, target)
            formula="AND(LEFT({Participant},7)='DEMO - ',REGEX_MATCH({Demo ID},'^AAA-DEMO-[0-9]+$'),OR({Email}='',REGEX_MATCH(LOWER({Email}),'@example[.]test$')))"
            for row in pipeline.records(config, source, formula):
                if row['id'] not in registered:
                    pipeline.capture(row, list(registered.values()))
            stamp = sources.stamp()
            result = dict(people=people, table_id=table, base_id=base, thinkific_data=thinkific,
                          airtable=dict(state='connected',last_success=stamp,record_count=len(people)),
                          thinkific=dict(state='connected',last_success=stamp),
                          assessment_connection=dict(state='connected',last_success=stamp),
                          events=[],refreshed_at=stamp,hosted_demo=True,hosted_mode='live',
                          read_only=True,local_only=False)
            return pipeline.apply_assessments(result)
        finally:
            pipeline.DB = previous

def dashboard(force=False):
    global CACHE, CACHE_AT
    with LOCK:
        missing = [key for key in REQUIRED if not os.environ.get(key)]
        if missing:
            value = baseline()
            value['missing_configuration'] = missing
            return value
        # A short cache bounds repeat clicks; it is optional, never authoritative.
        if CACHE is not None and time.monotonic()-CACHE_AT < (20 if force else 60):
            return copy.deepcopy(CACHE)
        try:
            value = read_live()
            CACHE, CACHE_AT = copy.deepcopy(value), time.monotonic()
            return value
        except Exception:
            # Provider responses can contain private details; return no raw errors.
            value = copy.deepcopy(CACHE) if CACHE is not None else baseline()
            value['hosted_mode'] = 'stale'
            value['hosted_error'] = 'Live refresh failed. Showing the last available source snapshot; check server configuration and provider access.'
            for key in ('airtable','thinkific','assessment_connection'):
                value[key] = {**value.get(key,{}),'state':'error','error':value['hosted_error']}
            for person in value['people']:
                if person.get('thinkific'):
                    person['progress_source']='Thinkific last verified snapshot; stale'
            print('Hosted source refresh failed; retained snapshot.', flush=True)
            return value

class handler(BaseHTTPRequestHandler):
    def send(self, status, value):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/health' or 'health' in parse_qs(parsed.query):
            return self.send(200,dict(ok=True,read_only=True))
        if parsed.path not in ('/api/dashboard','/api/dashboard/refresh'):
            return self.send(404,dict(error='Endpoint not found.'))
        return self.send(200,dashboard(force='refresh' in parse_qs(parsed.query)))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ('/api/dashboard/refresh','/api/dashboard') or (parsed.path=='/api/dashboard' and 'refresh' not in parse_qs(parsed.query)):
            return self.send(405,dict(error='The shared demo is read only. Run the local source project to edit.'))
        origin=self.headers.get('Origin')
        if origin and origin != 'https://'+self.headers.get('Host',''):
            return self.send(403,dict(error='Cross-origin refresh refused.'))
        return self.send(200,dashboard(force=True))
