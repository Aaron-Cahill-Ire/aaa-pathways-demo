"""Server-side adapters restricted to explicitly synthetic AAA demo records.

Run `python3 integrations.py sync` to refresh the local read model. Credentials
remain in ../.secrets or environment variables and are never returned to clients.
"""
import argparse
import csv
import io
import json
import os
import re
import threading
import time
import math
import fcntl
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
SNAPSHOT = DATA / 'dashboard-snapshot.json'
JOURNAL = DATA / 'dashboard-events.json'
class SourceLock:
    """Reentrant thread and host process lock for sync and writes."""
    def __init__(self):self.thread=threading.RLock();self.local=threading.local()
    def __enter__(self):
        self.thread.acquire()
        try:
            if not getattr(self.local,'depth',0):
                DATA.mkdir(parents=True,exist_ok=True);self.local.file=open(DATA/'source.lock','a')
                fcntl.flock(self.local.file,fcntl.LOCK_EX)
            self.local.depth=getattr(self.local,'depth',0)+1
        except BaseException:self.thread.release();raise
        return self
    def __exit__(self,*args):
        self.local.depth-=1
        if not self.local.depth:
            fcntl.flock(self.local.file,fcntl.LOCK_UN);self.local.file.close()
        self.thread.release()
LOCK = SourceLock()
DEMO_TABLE = 'DEMO Pathways Assessments'
FORMULA = "AND(REGEX_MATCH({Demo ID}, '^AAA-DEMO-[0-9]+$'), REGEX_MATCH(LOWER({Email}), '@example[.]test$'), LEFT({Participant}, 7) = 'DEMO - ')"
STAGES = ['Just joined', 'Learning', 'Needs follow-up', 'Completed', 'Assessment submitted - review']

class IntegrationError(Exception):
    def __init__(self, message, status=502):
        self.message, self.status = message, status
        super().__init__(message)

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def settings(service):
    path = ROOT.parent / '.secrets' / f'{service}.env'
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k:v for k,v in os.environ.items() if k.startswith(service.upper()+'_')})
    return values

def read_json(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text())

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as handle:
        json.dump(value,handle,indent=2);temp=handle.name
    os.replace(temp,path)

def request(url, token, method='GET', body=None):
    headers = {'Authorization':'Bearer '+token, 'Accept':'application/json',
               'User-Agent':'AAA-Pathways-Prototype/1.0', 'Content-Type':'application/json'}
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response: return json.load(response)
        except urllib.error.HTTPError as error:
            # Safe reads and keyed PATCH upserts can be retried. Unkeyed POST is never retried.
            if method in ('GET','PATCH') and error.code in (429,500,502,503,504) and attempt<2:
                try: delay=float(error.headers.get('Retry-After',2**attempt))
                except (TypeError,ValueError): delay=2**attempt
                time.sleep(min(max(delay,1),30)); continue
            raise IntegrationError(f'API returned HTTP {error.code}. Check account permissions, plan access and service availability.') from None
        except (urllib.error.URLError, TimeoutError):
            raise IntegrationError('Connection unavailable. Last successful snapshot is retained; pending keyed writes can be retried.') from None

def airtable_config():
    config = settings('airtable')
    if not config.get('AIRTABLE_TOKEN') or not config.get('AIRTABLE_BASE_ID'):
        raise IntegrationError('Airtable credentials have not been configured.', 503)
    return config

def airtable_url(config, table='', query=None):
    return 'https://api.airtable.com/v0/'+config['AIRTABLE_BASE_ID']+('/'+table if table else '')+('?' + urlencode(query) if query else '')

def find_table(config):
    schema = request('https://api.airtable.com/v0/meta/bases/'+config['AIRTABLE_BASE_ID']+'/tables', config['AIRTABLE_TOKEN'])
    table = next((t for t in schema.get('tables',[]) if t['name']==DEMO_TABLE), None)
    if not table: raise IntegrationError('The dedicated DEMO Pathways Assessments table was not found. No other table was read.')
    return table['id']

def is_demo(fields):
    return (bool(re.fullmatch(r'AAA-DEMO-[0-9]+', fields.get('Demo ID','')))
            and fields.get('Email','').lower().endswith('@example.test')
            and fields.get('Participant','').startswith('DEMO - '))

def normalise(row):
    f = row.get('fields', {})
    if not is_demo(f): raise IntegrationError('The record is not explicitly synthetic. Operation refused.', 403)
    total, completed = f.get('Total lessons'), f.get('Completed lessons')
    if not isinstance(total,(int,float)) or not isinstance(completed,(int,float)) or total<=0 or not 0<=completed<=total:
        raise IntegrationError('Invalid progress values in a demo record. Fix the source data before refreshing.')
    return {'id':row['id'], 'demo_id':f['Demo ID'], 'name':f['Participant'], 'email':f['Email'],
            'country':f.get('Country','Not recorded'), 'stage':f.get('Stage','Not recorded'),
            'completed':completed, 'total':total, 'percent':round(completed/total*100),
            'score':f.get('Demo score out of 2') if f.get('Q1') and f.get('Q2') else None,
            'q1':f.get('Q1',''), 'q2':f.get('Q2',''), 'reflection':f.get('Reflection',''),
            'next_action':f.get('Next action',''), 'provenance':f.get('Data provenance','Not recorded'),
            'created_at':row.get('createdTime'), 'source':'Airtable', 'thinkific':None,
            'progress_source':'Synthetic seed', 'thinkific_stored':f.get('Thinkific progress JSON')}

def pull_airtable():
    config = airtable_config(); table = find_table(config)
    import pipeline
    registered={p['id'] for p in pipeline.registry()['advocates']}
    people, offset = [], None
    while True:
        query = {'filterByFormula':FORMULA, 'pageSize':100}
        if offset: query['offset'] = offset
        data = request(airtable_url(config,table,query), config['AIRTABLE_TOKEN'])
        people.extend(normalise(row) for row in data.get('records', []) if row['id'] in registered)
        offset = data.get('offset')
        if not offset: break
    ids = [p['demo_id'] for p in people]
    if len(ids)!=len(set(ids)): raise IntegrationError('Duplicate Demo IDs found. Resolve the source records before refreshing.')
    return sorted(people,key=lambda p:p['demo_id']), table, config['AIRTABLE_BASE_ID']

def thinkific_get(endpoint, config, query=None):
    url = 'https://api.thinkific.com/api/public/v1/'+endpoint
    if query: url += '?' + urlencode(query)
    return request(url, config['THINKIFIC_API_TOKEN'])

def thinkific_items(endpoint, config, query=None):
    items=[];page=1
    while True:
        data=thinkific_get(endpoint,config,{**(query or {}),'page':page,'limit':100})
        items.extend(data.get('items',[]))
        if page>=data.get('meta',{}).get('pagination',{}).get('total_pages',1):return items
        page+=1

def pull_native_quizzes(config, mappings):
    if not mappings:return {'state':'not-checked','submissions':[]}
    # A named operation is required. Filter both course and explicitly mapped fictional users.
    values={'filter':{'courseIds':['3558004'],'userIds':[str(m['user_id']) for m in mappings]},'after':None}
    query='''query AAADemoQuiz($filter:QuizSubmissionFilter,$after:String){site{quizSubmissions(first:50,filter:$filter,after:$after){nodes{id attempts correctCount incorrectCount completedAt createdAt passed quiz{id name} user{id email}} pageInfo{hasNextPage endCursor}}}}'''
    results=[]
    while True:
        data=request('https://api.thinkific.com/stable/graphql',config['THINKIFIC_API_TOKEN'],'POST',{'query':query,'variables':values})
        if data.get('errors'):raise IntegrationError('Thinkific quiz GraphQL query failed; native quiz results remain unavailable.')
        connection=data['data']['site']['quizSubmissions']
        for item in connection['nodes']:
            if str(item['user']['id']) not in values['filter']['userIds']:raise IntegrationError('Native quiz returned an unmapped user. Refused.')
            # Quiz IDs are scoped independently from enrollment progress.
            results.append(item)
        info=connection['pageInfo']
        if not info['hasNextPage']:break
        if not info['endCursor'] or info['endCursor']==values['after']:raise IntegrationError('Invalid quiz pagination cursor.')
        values['after']=info['endCursor']
    return {'state':'verified','checked_at':stamp(),'submissions':results,
            'note':'GraphQL access verified. No stored quiz submissions for mapped fictional learners.' if not results else 'Native quiz submissions retrieved independently of progress.'}

def pull_thinkific(people):
    import pipeline
    config=settings('thinkific'); reg=pipeline.registry()
    if not config.get('THINKIFIC_API_TOKEN'):raise IntegrationError('Thinkific credentials have not been configured.',503)
    course=thinkific_get('courses/3558004',config)
    if course.get('id')!=reg['course_id'] or 'demo' not in course.get('name','').lower():raise IntegrationError('Demo course guard failed.')
    safe={k:course.get(k) for k in ['id','name','slug']};safe['chapters']=[]
    for ch in thinkific_items('courses/3558004/chapters',config):
        contents=thinkific_items(f'chapters/{ch["id"]}/contents',config)
        safe['chapters'].append({'id':ch['id'],'name':ch.get('name',ch.get('title','Demo section')),
            'lessons':[{'id':x['id'],'name':x.get('name',x.get('title','Demo lesson')),'type':x.get('type','')} for x in contents]})
    safe['lesson_count']=sum(len(ch['lessons']) for ch in safe['chapters'])
    matches=[]
    for mapping in reg['advocates']:
        if not mapping.get('thinkific_user_id'):continue
        p=next((p for p in people if p['id']==mapping['id']),None)
        if not p or any(p[k]!=mapping[k] for k in ['demo_id','email','name']):raise IntegrationError('Fixed advocate identity changed; Thinkific sync stopped.')
        user=thinkific_get(f'users/{mapping["thinkific_user_id"]}',config)
        if user.get('email','').lower()!=mapping['email'].lower() or user.get('first_name')!='DEMO':raise IntegrationError('Mapped Thinkific learner guard failed.')
        enrollments=thinkific_items('enrollments',config,{'query[user_id]':user['id'],'query[course_id]':3558004})
        exact=[e for e in enrollments if e.get('user_id')==user['id'] and e.get('course_id')==3558004]
        if len(exact)!=1 or exact[0]['id']!=mapping['thinkific_enrollment_id']:raise IntegrationError('Enrollment mapping missing or ambiguous; review required.')
        e=exact[0]
        try:ratio=float(e['percentage_completed'])
        except (TypeError,ValueError,KeyError):raise IntegrationError('Thinkific did not return valid progress; seeded counts retained.')
        if not math.isfinite(ratio) or not 0<=ratio<=1:raise IntegrationError('Thinkific progress must be a fraction from zero to one.')
        matches.append({'demo_id':p['demo_id'],'advocate_id':p['id'],'user_id':user['id'],'course_id':3558004,
            'enrollment_id':e['id'],'percentage_completed':ratio,'percent':round(ratio*100,2),
            'completed_at':e.get('completed_at'),'started_at':e.get('started_at'),'updated_at':e.get('updated_at'),
            'checked_at':stamp(),'source':'Thinkific enrollment API','lesson_count_available':False})
    try:quizzes=pull_native_quizzes(config,matches)
    except IntegrationError as error:quizzes={'state':'error','error':error.message,'submissions':[]}
    for e in matches:
        e['native_quizzes']={**quizzes,'submissions':[q for q in quizzes.get('submissions',[]) if str(q['user']['id'])==str(e['user_id'])]}
    return {'courses':[safe],'enrollments':matches,'matched_people':len(matches),
            'native_quizzes':quizzes,'subdomain':config.get('THINKIFIC_SUBDOMAIN',''),
            'course_access':'Unpublished course: API enrollment works; learner access and activity test require publication approval.'}

def persist_progress(people, data):
    import pipeline
    config=airtable_config();table=find_table(config)
    for e in data['enrollments']:
        row=request(airtable_url(config,table+'/'+e['advocate_id']),config['AIRTABLE_TOKEN']);fresh=normalise(row)
        p=next(p for p in people if p['id']==e['advocate_id'])
        if any(fresh[k]!=p[k] for k in ['demo_id','email','name']):raise IntegrationError('Remote advocate identity changed; progress write refused.')
        encoded=json.dumps(e,sort_keys=True)
        saved=request(airtable_url(config,table+'/'+p['id']),config['AIRTABLE_TOKEN'],'PATCH',{'fields':{pipeline.PROGRESS_FIELD:encoded}})
        if saved['fields'].get(pipeline.PROGRESS_FIELD)!=encoded:raise IntegrationError('Airtable progress write could not be verified.')
        # Counts remain the seeded baseline; the authoritative display uses source percentage only.
        p.update(thinkific=e,percent=e['percent'],completed=None,progress_source='Verified Thinkific API',thinkific_stored=encoded)


def empty_snapshot():
    return {'people':[], 'airtable':{'state':'unchecked'}, 'thinkific':{'state':'unchecked'},
            'thinkific_data':{'courses':[],'enrollments':[]}, 'refreshed_at':None}

def snapshot():
    with LOCK:
        result=read_json(SNAPSHOT,empty_snapshot())
        result['events']=read_json(JOURNAL,[])[-100:][::-1]
        result['local_only']=True
        import pipeline
        return pipeline.apply_assessments(result)

def sync():
    with LOCK:
        result=read_json(SNAPSHOT,empty_snapshot()); checked=stamp()
        try:
            previous={p['id']:p for p in result['people']}
            people, table, base = pull_airtable()
            for p in people:
                old=previous.get(p['id'],{})
                if old.get('thinkific') and all(old.get(k)==p[k] for k in ['demo_id','email','name']):
                    p.update(thinkific=old['thinkific'],percent=old['percent'],completed=None,progress_source='Verified Thinkific API; refresh pending')
            result.update(people=people,table_id=table,base_id=base)
            result['airtable']={'state':'connected','checked_at':checked,'last_success':stamp(),'record_count':len(people)}
        except IntegrationError as error:
            result['airtable']={**result['airtable'],'state':'error','checked_at':checked,'error':error.message}
        try:
            source_data=pull_thinkific(result['people'])
            persist_progress(result['people'],source_data)
            result['thinkific_data']=source_data
            result['thinkific']={'state':'connected','checked_at':checked,'last_success':stamp()}
        except IntegrationError as error:
            result['thinkific']={**result['thinkific'],'state':'error','checked_at':checked,'error':error.message}
            for p in result['people']:
                if p.get('thinkific'):p['progress_source']='Thinkific last verified snapshot; stale'
        try:
            import pipeline
            pipeline.ingest()
            result['assessment_connection']={'state':'connected','last_success':stamp()}
        except IntegrationError as error:
            result['assessment_connection']={**result.get('assessment_connection',{}),'state':'error','error':error.message}
        result['refreshed_at']=stamp()
        save_json(SNAPSHOT,result)
        return snapshot()

def update_demo(record_id, data):
    with LOCK:
        current=snapshot()
        p=next((p for p in current['people'] if p['id']==record_id),None)
        if not p: raise IntegrationError('Unknown demo record. Refresh the dashboard first.',404)
        allowed={'stage','next_action','q1','q2','reflection','event_key'}
        if not data or set(data)-allowed: raise IntegrationError('Unsupported demo update.',400)
        key=data.get('event_key','')
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,100}',key): raise IntegrationError('A valid event key is required.',400)
        if any(k in data for k in ['q1','q2','reflection']):raise IntegrationError('Use the assessment attempt endpoint to preserve retakes.',400)
        fields={}
        for name,field in [('stage','Stage'),('next_action','Next action'),('q1','Q1'),('q2','Q2'),('reflection','Reflection')]:
            if name in data:
                value=data[name]
                if not isinstance(value,str) or not value.strip() or len(value)>3000: raise IntegrationError('Invalid '+name+'.',400)
                fields[field]=value.strip()
        if not fields: raise IntegrationError('No changes supplied.',400)
        if 'stage' in data and data['stage'] not in STAGES: raise IntegrationError('Unknown stage.',400)
        if ('q1' in data)!=('q2' in data): raise IntegrationError('Provide both demo answers.',400)
        if any(data.get(q) not in ['A','B'] for q in ['q1','q2'] if q in data): raise IntegrationError('Demo answers must be A or B.',400)
        events=read_json(JOURNAL,[])
        existing=next((e for e in events if e['event_key']==key),None)
        if existing:
            if existing['record_id']!=record_id or existing['fields']!=fields: raise IntegrationError('Event key reused with different content.',409)
            if existing['state']=='saved': return {'saved':True,'replayed':True,'event_key':key}
        config=airtable_config(); table=find_table(config)
        # Verify current remote markers immediately before every write.
        before=request(airtable_url(config,table+'/'+record_id),config['AIRTABLE_TOKEN'])
        normalise(before)
        event=existing or {'event_key':key,'record_id':record_id,'demo_id':p['demo_id'],'at':stamp(),
                           'state':'pending','fields':fields,'before':before['fields']}
        if not existing: events.append(event)
        save_json(JOURNAL,events)
        row=request(airtable_url(config,table+'/'+record_id),config['AIRTABLE_TOKEN'],'PATCH',{'fields':fields})
        fresh=normalise(row)
        for field,value in fields.items():
            if row['fields'].get(field)!=value: raise IntegrationError('Remote update could not be verified. Refresh before retrying.')
        event.update(state='saved',saved_at=stamp(),after=row['fields'])
        save_json(JOURNAL,events)
        fresh.update({k:p[k] for k in ['thinkific','progress_source','percent','completed'] if k in p})
        current['people']=[fresh if x['id']==record_id else x for x in current['people']]
        current.pop('events',None); current['airtable'].update(state='connected',last_success=stamp())
        save_json(SNAPSHOT,current)
        return {'saved':True,'replayed':False,'event_key':key,'person':fresh}

def export_csv():
    buf=io.StringIO(newline=''); writer=csv.writer(buf)
    fields=['demo_id','name','email','country','stage','completed','total','percent','progress_source','score','assessment_source','next_action','provenance']
    writer.writerow(fields)
    for p in snapshot()['people']:
        values=[p.get(k,'') if p.get(k) is not None else '' for k in fields]
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in values])
    return buf.getvalue().encode('utf-8-sig')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['sync']);parser.parse_args()
    result=sync()
    print(json.dumps({'airtable':result['airtable'],'thinkific':result['thinkific'],
                      'demo_courses':result['thinkific_data'].get('courses',[]),
                      'matched_demo_learners':result['thinkific_data'].get('matched_people',0),
                      'demo_enrollments':result['thinkific_data'].get('enrollments',[])},indent=2))
