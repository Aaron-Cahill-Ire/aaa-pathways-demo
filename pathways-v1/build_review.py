"""Package a read-only, offline review and a source handoff without credentials."""
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import quote
import integrations

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'handoff'
OUT.mkdir(exist_ok=True)
state=integrations.snapshot()
script=(ROOT/'static/dashboard.js').read_text()
start=script.index('async function api(')
end=script.index('\nasync function load()',start)
script=script[:start]+'''async function api(path,body){if(path==='/api/dashboard'&&!body)return structuredClone(REVIEW_DATA);throw Error('This saved review copy is read only. Run the local source project to refresh or edit Airtable.');}'''+script[end:]
script=script.replace('function render(){','function renderInner(){',1)
script=script.replace("app.addEventListener('input'",'''function render(){renderInner();document.querySelectorAll('form input,form textarea,form select,form button,[data-action="refresh"]').forEach(el=>el.disabled=true);}
app.addEventListener('input' ''',1)
script=script.replace('WORKING PROTOTYPE','SAVED REVIEW COPY')
script=script.replace("'Airtable API verified'","'Verified Airtable snapshot'")
script=script.replace('↻ Refresh sources','Saved source snapshot')
script=script.replace('Fictional people ·','Read-only review · fictional people ·')
script=script.replace('href="/handoff/contractor.docx"','href="AAA Dashboard Contractor Handoff.docx"')
script=script.replace('href="/handoff/decisions.docx"','href="AAA Dashboard Decisions for AAA.docx"')
csv_url='data:text/csv;charset=utf-8,'+quote(integrations.export_csv().decode('utf-8-sig'))
script=script.replace('href="/api/dashboard/export"',f'href="{csv_url}" download="aaa-demo-advocates.csv"')
script=script.replace('The old <a href="/learner#/learn">six-section learner preview ↗</a> remains a separate local demonstration.','The older six-section learner preview is included in the contractor source bundle.')
script=script.replace('This simulator replaces the sample answers in this Airtable demo record and keeps a local before-and-after log. It is not a connected Google Form.','The live prototype can replace sample answers in Airtable and keep a local before-and-after log. Editing is disabled in this saved review copy. Google Forms is not connected.')
script=script.replace('Each submission creates a separate fictional attempt in Airtable. Retakes are preserved.', 'This saved review shows separate Airtable attempts and retained retakes. Editing is disabled.')
script=script.replace('Writes only to this fictional record. No message is sent.','Editing is disabled in this saved review copy.')
data=json.dumps(state,ensure_ascii=False).replace('</','<\\/')
html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AAA Pathways Dashboard Review</title><style>'+(ROOT/'static/dashboard.css').read_text()+'</style></head><body class="offline"><a class="skip" href="#main">Skip to content</a><div id="app"></div><div id="toast" role="status" aria-live="polite"></div><script type="module">const REVIEW_DATA='+data+';\n'+script+'</script></body></html>'
(OUT/'AAA Dashboard Review.html').write_text(html)
# Retain the generated script for a syntax check, outside the deliverables.
check=ROOT/'test-results/review-script.mjs';check.parent.mkdir(exist_ok=True);check.write_text('const REVIEW_DATA='+data+';\n'+script)
archive=OUT/'AAA Dashboard Contractor Bundle.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in ROOT.rglob('*'):
        rel=path.relative_to(ROOT)
        if not path.is_file() or any(p in {'__pycache__','test-results','.git'} for p in rel.parts):continue
        if rel.parts[0]=='data' and rel.name!='dashboard-snapshot.json':continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if rel.as_posix()=='data/dashboard-snapshot.json':z.writestr('AAA Dashboard/pathways-v1/data/dashboard-snapshot.json',json.dumps(state,indent=2))
        else:z.write(path,Path('AAA Dashboard')/'pathways-v1'/rel)
    for name in ['AAA Dashboard Contractor Handoff.docx','AAA Dashboard Decisions for AAA.docx','AAA Dashboard Review.html','AAA Dashboard Preview.png','AAA Dashboard Record Example.png']:
        z.write(OUT/name,Path('AAA Dashboard')/'handoff'/name)
    for name in ['demo_records.json','DEMO_Pathways_Assessments.csv','source_registry.json','integration_manifest.json','live_integration_evidence.json']:
        z.write(ROOT.parent/'thinkific-demo'/name,'AAA Dashboard/thinkific-demo/'+name)
    z.writestr('AAA Dashboard/.gitignore','.secrets/\n.artifacts/\n__pycache__/\n*.pyc\npathways-v1/data/\npathways-v1/test-results/\n')
with zipfile.ZipFile(archive) as z:
    assert not any('.secrets' in Path(n).parts or n.endswith('.sqlite3') for n in z.namelist())
    for service in ['airtable','thinkific']:
        token=integrations.settings(service).get(service.upper()+'_TOKEN') or integrations.settings(service).get(service.upper()+'_API_TOKEN')
        if token:
            for name in z.namelist():
                assert token.encode() not in z.read(name),'Credential must not enter the source bundle.'
with zipfile.ZipFile(OUT/'AAA Dashboard Review Pack.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in ['AAA Dashboard Contractor Handoff.docx','AAA Dashboard Decisions for AAA.docx','AAA Dashboard Review.html','AAA Dashboard Preview.png','AAA Dashboard Record Example.png']:
        z.write(OUT/name,name)
    z.writestr('START HERE.txt','Open AAA Dashboard Review.html in your browser. It is a saved, read-only review with fictional participants. Keep the two Word documents in the same folder for the dashboard download links. The contractor handoff explains the working connections and remaining build; the decision brief covers choices for AAA. No credentials or live API calls are included.\n')
print('Created offline review, review pack and credential-free contractor source bundle.')
