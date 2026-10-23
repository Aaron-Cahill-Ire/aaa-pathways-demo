"""Fictional-only source ingestion. SQLite journal plus idempotent Airtable outbox.

The fixed registry is the identity authority. Form fields are claimed identity,
never sign-in. No scheduling or production identity verification is implied.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import integrations as a

REGISTRY = a.ROOT.parent / 'thinkific-demo/source_registry.json'
DB = a.DATA / 'source-events.sqlite3'
ATTEMPTS_TABLE = 'DEMO Assessment Attempts'
PROGRESS_FIELD = 'Thinkific progress JSON'
SOURCE_FIELD = 'Submission request key'
FORM_ID = 'pagk5GhaNoKEmxpLv'

def registry():
    r = a.read_json(REGISTRY, {})
    if r.get('course_id') != 3558004 or len(r.get('advocates', [])) != 6:
        raise a.IntegrationError('The fixed fictional source registry is missing or invalid.')
    for p in r['advocates']:
        if not a.is_demo({'Participant':p['name'], 'Demo ID':p['demo_id'], 'Email':p['email']}):
            raise a.IntegrationError('Non-fictional identity in source registry. Refused.',403)
    return r

@contextmanager
def database():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(DB,timeout=30); db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS attempts (
      source_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
      advocate_id TEXT, match_state TEXT NOT NULL, reason TEXT NOT NULL,
      score INTEGER, received_at TEXT NOT NULL, mirrored_id TEXT, mirror_error TEXT);
    CREATE TABLE IF NOT EXISTS conflicts (
      source_key TEXT NOT NULL, payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
      reason TEXT NOT NULL, received_at TEXT NOT NULL,
      PRIMARY KEY(source_key,payload_hash));
    CREATE TABLE IF NOT EXISTS requests (
      request_key TEXT PRIMARY KEY, payload TEXT NOT NULL, source_id TEXT);
    ''')
    try:
        db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
    except BaseException:
        db.rollback(); raise
    finally: db.close()

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()

def schema(config):
    return a.request('https://api.airtable.com/v0/meta/bases/'+config['AIRTABLE_BASE_ID']+'/tables',config['AIRTABLE_TOKEN'])['tables']

def setup():
    """Explicit schema-only setup; never mutate any non-demo table."""
    registry(); c=a.airtable_config(); tables=schema(c)
    source=next(t for t in tables if t['name']==a.DEMO_TABLE)
    meta='https://api.airtable.com/v0/meta/bases/'+c['AIRTABLE_BASE_ID']+'/tables'
    for name in [PROGRESS_FIELD,SOURCE_FIELD]:
        if name not in [f['name'] for f in source['fields']]:
            a.request(meta+'/'+source['id']+'/fields',c['AIRTABLE_TOKEN'],'POST',{'name':name,'type':'multilineText'})
    table=next((t for t in tables if t['name']==ATTEMPTS_TABLE),None)
    if not table:
        fields=[{'name':n,'type':'multilineText'} for n in ['Source key','Payload JSON']]
        table=a.request(meta,c['AIRTABLE_TOKEN'],'POST',{'name':ATTEMPTS_TABLE,'description':'Immutable fictional assessment snapshots. Review claims; never authentication.','fields':fields})
    return {'source_table':source['id'],'attempts_table':table['id']}

def table_ids(c):
    tables=schema(c)
    names={t['name']:t['id'] for t in tables}
    if ATTEMPTS_TABLE not in names: raise a.IntegrationError('Run pipeline.py setup before ingestion.')
    return names[a.DEMO_TABLE],names[ATTEMPTS_TABLE]

def records(c,table,formula=None):
    rows=[]; offset=None
    while True:
        query={'pageSize':100}
        if formula:query['filterByFormula']=formula
        if offset:query['offset']=offset
        result=a.request(a.airtable_url(c,table,query),c['AIRTABLE_TOKEN'])
        rows.extend(result.get('records',[])); offset=result.get('offset')
        if not offset:return rows

def match_claim(payload, identities):
    f=payload['fields']; claimed=f.get('Demo ID','').strip()
    choices=[p for p in identities if p['demo_id']==claimed]
    if len(choices)!=1: return None,'unmatched','No unique registered advocate for the claimed Demo ID.'
    p=choices[0]
    if f.get('Participant','').strip().casefold()!=p['name'].casefold():
        return None,'conflict','Claimed Demo ID and participant name disagree.'
    if f.get('Email') and f['Email'].strip().casefold()!=p['email'].casefold():
        return None,'conflict','Claimed Demo ID and email disagree.'
    if any(f.get(q) not in ['A','B'] for q in ['Q1','Q2']):
        return None,'incomplete','Both answers are required; a missing score is not zero.'
    return p['id'],'matched-demo','Fixed fictional ID and exact name agree; submitter identity is not authenticated.'

def capture(row, identities):
    f=row.get('fields',{})
    # Only explicitly fictional source rows. No real email or participant is retained.
    if not f.get('Participant','').startswith('DEMO - ') or not __import__('re').fullmatch(r'AAA-DEMO-[0-9]+',f.get('Demo ID','')):
        return None
    if f.get('Email') and not f['Email'].strip().lower().endswith('@example.test'):return None
    payload={'source':'airtable-private-form-inbox','source_record_id':row['id'],'form_id':FORM_ID,
             'submitted_at':row.get('createdTime'),'assessment_version':registry()['assessment_id'],
             'rubric_version':registry()['rubric_version'],
             'fields':{k:f.get(k,'') for k in ['Demo ID','Participant','Email','Q1','Q2','Reflection']}}
    key='airtable:'+row['id']; h=digest(payload)
    pid,state,reason=match_claim(payload,identities)
    score=sum(f[q]=='A' for q in ['Q1','Q2']) if all(f.get(q) in ['A','B'] for q in ['Q1','Q2']) else None
    with database() as db:
        old=db.execute('SELECT * FROM attempts WHERE source_key=?',(key,)).fetchone()
        if old:
            if old['payload_hash']!=h:
                db.execute('INSERT OR IGNORE INTO conflicts VALUES (?,?,?,?,?)',(key,h,canonical(payload),'Source record changed after capture; original attempt remains immutable.',a.stamp()))
            return key
        db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,NULL,NULL)',(key,h,canonical(payload),pid,state,reason,score,a.stamp()))
    return key

def attempt_fields(attempt):
    envelope={k:attempt[k] for k in ['source_key','payload_hash','advocate_id','match_state','reason','score','received_at']}
    envelope['payload']=json.loads(attempt['payload'])
    envelope['identity_assurance']='Fictional claim match only; not authenticated'
    return {'Source key':attempt['source_key'],'Payload JSON':canonical(envelope)}


def mirror(c,table):
    with database() as db: pending=[dict(r) for r in db.execute('SELECT * FROM attempts WHERE mirrored_id IS NULL ORDER BY received_at,source_key')]
    for item in pending:
        try:
            fields=attempt_fields(item)
            found=records(c,table,"{Source key}='"+item['source_key']+"'")
            if len(found)>1: raise a.IntegrationError('Duplicate attempt source key in Airtable; manual review required.')
            if found:
                row=found[0]
            else:
                response=a.request(a.airtable_url(c,table),c['AIRTABLE_TOKEN'],'PATCH',{'performUpsert':{'fieldsToMergeOn':['Source key']},'records':[{'fields':fields}]})
                row=response['records'][0]
            for key,value in fields.items():
                if row['fields'].get(key,'')!=value:raise a.IntegrationError('Airtable attempt differs from immutable local snapshot. Review required.')
            with database() as db:db.execute('UPDATE attempts SET mirrored_id=?, mirror_error=NULL WHERE source_key=?',(row['id'],item['source_key']))
        except a.IntegrationError as e:
            with database() as db:db.execute('UPDATE attempts SET mirror_error=? WHERE source_key=?',(e.message,item['source_key']))
            raise

def assessment_state():
    with database() as db:
        result=[dict(r) for r in db.execute('SELECT * FROM attempts ORDER BY json_extract(payload,\'$.submitted_at\'),source_key')]
        conflicts=[dict(r) for r in db.execute('SELECT * FROM conflicts ORDER BY received_at')]
    for r in result:r['payload']=json.loads(r['payload'])
    for r in conflicts:r['payload']=json.loads(r['payload']);r['match_state']='source-conflict'
    return {'attempts':result,'review': [r for r in result if r['match_state']!='matched-demo']+conflicts,
            'pending_mirrors':sum(not r['mirrored_id'] for r in result),'identity_assurance':'Demo claim matching only; not learner authentication.'}

def restore_attempts(c,target):
    """Recover missing local attempt rows from immutable Airtable envelopes.

    Private Airtable access remains the trust boundary. Hashes detect drift; they
    do not authenticate the person who originally submitted the form.
    """
    remote=records(c,target,"LEFT({Source key},9)='airtable:'")
    identities=registry()['advocates'];known={x['id'] for x in identities}
    for row in remote:
        try:
            envelope=json.loads(row['fields']['Payload JSON']);payload=envelope['payload'];key=envelope['source_key']
            if key!=row['fields']['Source key'] or key!='airtable:'+payload['source_record_id'] or digest(payload)!=envelope['payload_hash']:
                raise ValueError('Integrity mismatch')
            fields=payload['fields']
            if not fields['Participant'].startswith('DEMO - ') or not __import__('re').fullmatch(r'AAA-DEMO-[0-9]+',fields['Demo ID']):raise ValueError('Not fictional')
            if fields.get('Email') and not fields['Email'].lower().endswith('@example.test'):raise ValueError('Not fictional')
            if envelope['advocate_id'] is not None and envelope['advocate_id'] not in known:raise ValueError('Unknown advocate')
            expected,match,reason=match_claim(payload,identities)
            if (expected,match)!=(envelope['advocate_id'],envelope['match_state']):raise ValueError('Match contract differs')
            score=sum(fields[q]=='A' for q in ['Q1','Q2']) if all(fields.get(q) in ['A','B'] for q in ['Q1','Q2']) else None
            if score!=envelope['score']:raise ValueError('Score differs')
        except (KeyError,ValueError,TypeError):raise a.IntegrationError('Airtable attempt envelope failed validation. Restore stopped; review required.') from None
        with database() as db:
            old=db.execute('SELECT * FROM attempts WHERE source_key=?',(key,)).fetchone()
            if old:
                expected_fields=attempt_fields(dict(old))
                if any(row['fields'].get(k,'')!=v for k,v in expected_fields.items()):raise a.IntegrationError('Airtable immutable attempt changed. Review required.')
            else:
                db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,NULL)',(key,envelope['payload_hash'],canonical(payload),envelope['advocate_id'],envelope['match_state'],envelope['reason'],envelope['score'],envelope['received_at'],row['id']))
    return len(remote)

def ingest():
    with a.LOCK:
        r=registry();c=a.airtable_config();source,target=table_ids(c)
        # Recheck each fixed identity remotely; reject drift before matching submissions.
        for p in r['advocates']:
            row=a.request(a.airtable_url(c,source+'/'+p['id']),c['AIRTABLE_TOKEN']);fresh=a.normalise(row)
            if any(fresh[k]!=p[k] for k in ['id','demo_id','name','email']):raise a.IntegrationError('Registered advocate identity changed. Reconcile before ingestion.')
        restore_attempts(c,target)
        known={p['id'] for p in r['advocates']}
        formula="AND(LEFT({Participant},7)='DEMO - ',REGEX_MATCH({Demo ID},'^AAA-DEMO-[0-9]+$'),OR({Email}='',REGEX_MATCH(LOWER({Email}),'@example[.]test$')))"
        for row in records(c,source,formula):
            if row['id'] not in known:capture(row,r['advocates'])
        mirror(c,target)
        return assessment_state()

def submit_attempt(record_id,data):
    """Staff demo form → new source row → immutable attempt. Retry key is not identity."""
    with a.LOCK:
        if set(data)-{'q1','q2','reflection','event_key'}:raise a.IntegrationError('Unsupported attempt fields.',400)
        if not __import__('re').fullmatch('[a-zA-Z0-9_-]{8,100}',str(data.get('event_key',''))):raise a.IntegrationError('Valid event key required.',400)
        if any(data.get(q) not in ['A','B'] for q in ['q1','q2']):raise a.IntegrationError('Provide both answers.',400)
        if not isinstance(data.get('reflection'),str) or not 10<=len(data['reflection'].strip())<=3000:raise a.IntegrationError('Add a fictional reflection of 10 to 3000 characters.',400)
        p=next((p for p in registry()['advocates'] if p['id']==record_id),None)
        if not p:raise a.IntegrationError('Unknown fictional advocate.',404)
        fields={'Participant':p['name'],'Demo ID':p['demo_id'],'Email':p['email'],'Q1':data['q1'],'Q2':data['q2'],'Reflection':data['reflection'].strip(),SOURCE_FIELD:data['event_key']}
        value=canonical(fields)
        with database() as db:
            prior=db.execute('SELECT * FROM requests WHERE request_key=?',(data['event_key'],)).fetchone()
            if prior and prior['payload']!=value:raise a.IntegrationError('Retry key reused with changed content.',409)
            replay=bool(prior)
            db.execute('INSERT OR IGNORE INTO requests VALUES (?,?,NULL)',(data['event_key'],value))
        c=a.airtable_config();source,_=table_ids(c)
        current=a.normalise(a.request(a.airtable_url(c,source+'/'+p['id']),c['AIRTABLE_TOKEN']))
        if any(current[k]!=p[k] for k in ['id','demo_id','name','email']):raise a.IntegrationError('Advocate identity changed; review required.')
        found=records(c,source,"{"+SOURCE_FIELD+"}='"+data['event_key']+"'")
        if len(found)>1:raise a.IntegrationError('Duplicate source retry key; review required.',409)
        if found:row=found[0]
        else:
            response=a.request(a.airtable_url(c,source),c['AIRTABLE_TOKEN'],'PATCH',{'performUpsert':{'fieldsToMergeOn':[SOURCE_FIELD]},'records':[{'fields':fields}]})
            row=response['records'][0]
        if any(row['fields'].get(k)!=v for k,v in fields.items()):raise a.IntegrationError('Submission source write could not be verified.')
        with database() as db:db.execute('UPDATE requests SET source_id=? WHERE request_key=?',(row['id'],data['event_key']))
        ingest();a.sync()
        return {'saved':True,'replayed':replay,'source_record_id':row['id'],'source_key':'airtable:'+row['id']}

def apply_assessments(result):
    state=assessment_state();result['assessments']=state
    for p in result['people']:
        own=[x for x in state['attempts'] if x['advocate_id']==p['id'] and x['match_state']=='matched-demo']
        p['attempts']=own
        p['assessment_source']='Synthetic seed' if not own else 'Verified Airtable submission; fictional identity claim'
        if own:
            latest=own[-1];p['score']=latest['score']
            p.update({k:latest['payload']['fields'][f] for k,f in [('q1','Q1'),('q2','Q2'),('reflection','Reflection')]})
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['setup','ingest']);args=parser.parse_args()
    print(json.dumps(setup() if args.command=='setup' else ingest(),indent=2))
