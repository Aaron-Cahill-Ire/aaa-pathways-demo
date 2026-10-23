"""Build the hosted, read-only dashboard without credentials or vendor calls."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'

def build():
    OUT.mkdir(exist_ok=True)
    static = ROOT / 'pathways-v1/static'
    shutil.copyfile(static / 'index.html', OUT / 'index.html')
    shutil.copyfile(static / 'dashboard.css', OUT / 'dashboard.css')
    script = (static / 'dashboard.js').read_text()
    script = script.replace('function render(){', 'function renderInner(){', 1)
    marker = "app.addEventListener('input'"
    wrapper = '''function render(){
      renderInner();
      document.querySelectorAll('form input,form textarea,form select,form button').forEach(el=>el.disabled=true);
      const banner=document.querySelector('.demo-banner');
      banner.innerHTML=`<span>Fictional advocates · Read-only shared demo · No emails sent</span><span>${state.hosted_mode==='live'?'Live sources checked':'Saved source snapshot'} ${time(state.refreshed_at)}</span>`;
      const main=document.getElementById('main');
      const notice=document.createElement('div'); notice.className='notice';
      notice.textContent=state.hosted_mode==='live'
        ? 'This shared demo reads Airtable and Thinkific. Editing is available in the local source project.'
        : 'Showing the populated snapshot from the local Airtable and Thinkific integration. Live refresh needs server-side credentials in Vercel. Editing is available in the local source project.';
      main.prepend(notice);
      if(state.hosted_error){const warning=document.createElement('div');warning.className='notice warning';warning.textContent=state.hosted_error;main.prepend(warning);}
      document.querySelectorAll('.connection .badge').forEach(el=>{
        if(el.textContent==='Connected'&&state.hosted_mode!=='live'){el.textContent='Saved snapshot';el.className='badge amber';}
      });
    }
    app.addEventListener('input' '''
    assert marker in script
    script = script.replace(marker, wrapper, 1)
    changes = {
        'WORKING PROTOTYPE': 'SHARED DEMO',
        "'Airtable API verified'": "'Airtable source evidence'",
        'Each submission creates a separate fictional attempt in Airtable. Retakes are preserved.':
            'The local source project creates separate fictional attempts in Airtable and preserves retakes. Editing is disabled in this shared view.',
        'Save demo assessment to Airtable →': 'Assessment editing available locally',
        'Writes only to this fictional record. No message is sent.': 'Editing is available in the local source project. No message is sent.',
        'Local preview access.': 'Shared preview access.',
        'Keep fictional data on this computer.': 'Only the six pinned fictional advocates are exposed.',
        'The old <a href="/learner#/learn">six-section learner preview ↗</a> remains a separate local demonstration.':
            'The separate six-section learner preview is included in the GitHub source for local use.',
        'Saved and verified in Airtable. No email sent.': 'This shared view is read only.',
        'Reads and guarded updates use the real API.': 'Source evidence is shown here; guarded updates are available in the local project.',
        "toast(ok?'Sources refreshed.':'A connection needs attention. See Connections.',!ok)":
            "toast(state.hosted_mode==='live'?'Live sources refreshed.':'Saved snapshot loaded; live credentials are not configured.',!ok)",
        'Start the local server, then reload this page.': 'Please reload this page or try again shortly.',
    }
    for old, new in changes.items():
        script = script.replace(old, new)
    # Export exactly what is on screen, including a refreshed live response.
    script += '''
    app.addEventListener('click',e=>{
      const link=e.target.closest('a[href="/api/dashboard/export"]');if(!link)return;e.preventDefault();
      const keys=['demo_id','name','email','country','stage','percent','progress_source','score','assessment_source','next_action'];
      const cell=v=>{let s=String(v??'');if(/^[\\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
      const csv='\\uFEFF'+[keys,...state.people.map(p=>keys.map(k=>p[k]))].map(r=>r.map(cell).join(',')).join('\\r\\n');
      const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
      const a=document.createElement('a');a.href=url;a.download='aaa-demo-advocates.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    '''
    (OUT / 'dashboard.js').write_text(script)
    handoff = OUT / 'handoff'
    handoff.mkdir(exist_ok=True)
    for slug, name in [('contractor','AAA Dashboard Contractor Handoff.docx'),('decisions','AAA Dashboard Decisions for AAA.docx')]:
        shutil.copyfile(ROOT / 'handoff' / name, handoff / (slug+'.docx'))
    print('Built shared dashboard and handoff downloads; no credentials or API calls used.')

if __name__ == '__main__':
    build()
