"""Install the saved fictional snapshot in a fresh clone, without API calls.

Existing snapshots and journals are preserved. Use integrations.py sync for
subsequent live refreshes after configuring your own source credentials.
"""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pathways-v1'))
import pipeline

def bootstrap(destination=ROOT):
    data=Path(destination)/'pathways-v1/data'
    data.mkdir(parents=True,exist_ok=True)
    snapshot=json.loads((ROOT/'web-demo/data/snapshot.json').read_text())
    for filename,value in [('dashboard-snapshot.json',snapshot),('dashboard-events.json',snapshot.get('events',[]))]:
        target=data/filename
        if not target.exists():target.write_text(json.dumps(value,indent=2)+'\n')
    target=data/'source-events.sqlite3'
    if not target.exists():
        previous=pipeline.DB
        pipeline.DB=target
        try:
            with pipeline.database() as db:
                for attempt in snapshot['assessments']['attempts']:
                    db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)',(
                        attempt['source_key'],attempt['payload_hash'],pipeline.canonical(attempt['payload']),
                        attempt['advocate_id'],attempt['match_state'],attempt['reason'],attempt['score'],
                        attempt['received_at'],attempt['mirrored_id'],attempt.get('mirror_error')))
        finally:pipeline.DB=previous
    print('Saved fictional profiles and assessment history are ready. Existing local files were preserved.')

if __name__=='__main__':bootstrap()
