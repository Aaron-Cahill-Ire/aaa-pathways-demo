import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import integrations as app
import pipeline

def row():
    return {'id':'recGeNBArbf48utG1','fields':{'Participant':'DEMO - Sample','Demo ID':'AAA-DEMO-006','Email':'sample@example.test','Country':'Uganda','Stage':'Learning','Completed lessons':6,'Total lessons':12,'Q1':'B','Q2':'B','Demo score out of 2':0,'Next action':'Review sample'}}

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.paths=patch.multiple(app,SNAPSHOT=Path(self.temp.name)/'snapshot.json',JOURNAL=Path(self.temp.name)/'events.json');self.paths.start()
        self.pipeline_paths=patch.object(pipeline,'DB',Path(self.temp.name)/'events.sqlite3');self.pipeline_paths.start()
        state=app.empty_snapshot();state['people']=[app.normalise(row())]
        state['airtable']={'state':'connected','last_success':'2026-10-23T12:00:00Z'};app.save_json(app.SNAPSHOT,state)
    def tearDown(self):
        self.paths.stop();self.pipeline_paths.stop();self.temp.cleanup()
    def test_zero_and_missing_scores(self):
        self.assertEqual(app.normalise(row())['score'],0)
        r=row();r['fields'].pop('Q1');self.assertIsNone(app.normalise(r)['score'])
    def test_three_synthetic_markers_required(self):
        for field,value in [('Email','person@real.org'),('Participant','A real name'),('Demo ID','real-123')]:
            r=row();r['fields'][field]=value
            with self.assertRaises(app.IntegrationError):app.normalise(r)
    def test_pagination_keeps_demo_filter(self):
        with patch.object(app,'airtable_config',return_value={'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'}),patch.object(app,'find_table',return_value='tblDemo'),patch.object(app,'request',side_effect=[{'records':[row()],'offset':'next'},{'records':[]}]) as request:
            people,_,_=app.pull_airtable();self.assertEqual(len(people),1)
            for call in request.call_args_list:self.assertIn('filterByFormula=',call.args[0]);self.assertIn('example',call.args[0])
            self.assertIn('offset=next',request.call_args_list[1].args[0])
    def test_duplicate_ids_rejected(self):
        with patch.object(app,'airtable_config',return_value={'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'}),patch.object(app,'find_table',return_value='tblDemo'),patch.object(app,'request',return_value={'records':[row(),row()]}):
            with self.assertRaises(app.IntegrationError):app.pull_airtable()
    def test_remote_demo_markers_rechecked_before_write(self):
        r=row();r['fields']['Email']='someone@real.org'
        with patch.object(app,'airtable_config',return_value={'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'}),patch.object(app,'find_table',return_value='tblDemo'),patch.object(app,'request',return_value=r) as request:
            with self.assertRaises(app.IntegrationError):app.update_demo('recGeNBArbf48utG1',{'next_action':'New sample action','event_key':'test-event-001'})
            self.assertEqual(request.call_count,1);self.assertFalse(app.JOURNAL.exists())
    def test_write_verified_and_replay_does_not_patch_twice(self):
        after=row();after['fields']['Next action']='New sample action';payload={'next_action':'New sample action','event_key':'test-event-002'}
        with patch.object(app,'airtable_config',return_value={'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'}),patch.object(app,'find_table',return_value='tblDemo'),patch.object(app,'request',side_effect=[row(),after]) as request:
            self.assertTrue(app.update_demo('recGeNBArbf48utG1',payload)['saved']);self.assertTrue(app.update_demo('recGeNBArbf48utG1',payload)['replayed'])
            self.assertEqual(request.call_count,2);self.assertEqual(app.snapshot()['people'][0]['next_action'],'New sample action')
            self.assertEqual(app.snapshot()['events'][0]['before']['Next action'],'Review sample')
            with self.assertRaises(app.IntegrationError):app.update_demo('recGeNBArbf48utG1',{**payload,'next_action':'Changed payload'})
    def test_unknown_records_and_fields_never_reach_api(self):
        with patch.object(app,'request') as request:
            for record,data in [('recUnknown',{'event_key':'test-003','next_action':'Sample'}),('recGeNBArbf48utG1',{'event_key':'test-004','Email':'person@real.org'})]:
                with self.assertRaises(app.IntegrationError):app.update_demo(record,data)
            request.assert_not_called()
    def test_refresh_failure_retains_last_success(self):
        with patch.object(app,'pull_airtable',side_effect=app.IntegrationError('Airtable unavailable')),patch.object(app,'pull_thinkific',side_effect=app.IntegrationError('Thinkific unavailable')),patch.object(pipeline,'ingest',side_effect=app.IntegrationError('Unavailable')):
            state=app.sync();self.assertEqual(len(state['people']),1);self.assertEqual(state['airtable']['state'],'error')
            self.assertEqual(state['airtable']['last_success'],'2026-10-23T12:00:00Z')
    def test_csv_escapes_formulas_and_preserves_zero(self):
        s=app.snapshot();s['people'][0]['next_action']='=1+2';app.save_json(app.SNAPSHOT,s)
        csv=app.export_csv().decode('utf-8-sig');self.assertIn("'=1+2",csv);self.assertIn(',0,',csv)
    def test_stale_live_progress_not_replaced_with_seed_on_outage(self):
        state=app.snapshot();person=state['people'][0];person.update(thinkific={'enrollment_id':123},percent=0,completed=None,progress_source='Verified Thinkific API');app.save_json(app.SNAPSHOT,state)
        with patch.object(app,'pull_airtable',return_value=([app.normalise(row())],'tblDemo','appTest')),patch.object(app,'pull_thinkific',side_effect=app.IntegrationError('Unavailable')),patch.object(pipeline,'ingest',side_effect=app.IntegrationError('Unavailable')):
            result=app.sync();self.assertEqual(result['people'][0]['percent'],0);self.assertIsNone(result['people'][0]['completed']);self.assertIn('stale',result['people'][0]['progress_source'])
