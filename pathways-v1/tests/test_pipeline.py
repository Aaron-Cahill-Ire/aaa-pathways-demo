import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import integrations as a
import pipeline as p

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(p,'DB',Path(self.tmp.name)/'events.db');self.dbpatch.start()
        self.identity=p.registry()['advocates'][-1]
    def tearDown(self):self.dbpatch.stop();self.tmp.cleanup()
    def row(self,record='recFictional001',q1='B',q2='B',**changes):
        fields={'Participant':self.identity['name'],'Demo ID':self.identity['demo_id'],'Q1':q1,'Q2':q2,'Reflection':'Fictional test reflection'}
        fields.update(changes)
        return {'id':record,'createdTime':'2026-10-23T13:00:00.000Z','fields':fields}
    def capture(self,row):return p.capture(row,p.registry()['advocates'])
    def test_native_form_match_zero_retakes_and_replay(self):
        first=self.row();second=self.row('recFictional002','A','A')
        self.capture(first);self.capture(second);self.capture(first);self.capture(second)
        state=p.assessment_state();self.assertEqual(len(state['attempts']),2)
        self.assertEqual([r['score'] for r in state['attempts']],[0,2]);self.assertEqual(state['review'],[])
        self.assertTrue(all(r['advocate_id']==self.identity['id'] for r in state['attempts']))
    def test_same_source_changed_never_replaces_attempt(self):
        row=self.row();self.capture(row);changed=copy.deepcopy(row);changed['fields']['Q1']='A'
        self.capture(changed);self.capture(changed)
        state=p.assessment_state();self.assertEqual(len(state['attempts']),1);self.assertEqual(state['attempts'][0]['score'],0)
        self.assertEqual(len(state['review']),1);self.assertEqual(state['review'][0]['match_state'],'source-conflict')
    def test_identifier_alone_is_insufficient(self):
        self.capture(self.row(Participant='DEMO - Someone Else'))
        result=p.assessment_state()['attempts'][0];self.assertIsNone(result['advocate_id']);self.assertEqual(result['match_state'],'conflict')
    def test_conflicting_email_and_unknown_id_reviewed(self):
        self.capture(self.row(Email='other@example.test'));self.capture(self.row('recUnknown001',**{'Demo ID':'AAA-DEMO-999'}))
        state=p.assessment_state();self.assertEqual(len(state['review']),2);self.assertTrue(all(r['advocate_id'] is None for r in state['attempts']))
    def test_missing_score_never_becomes_zero(self):
        self.capture(self.row(q1=''));r=p.assessment_state()['attempts'][0]
        self.assertIsNone(r['score']);self.assertEqual(r['match_state'],'incomplete')
    def test_nonfictional_data_not_retained(self):
        self.assertIsNone(self.capture(self.row(Participant='Someone')))
        self.assertIsNone(self.capture(self.row(Email='real@organization.org')))
        self.assertEqual(p.assessment_state()['attempts'],[])
    def test_failed_mirror_retained_and_ambiguous_timeout_reconciled(self):
        self.capture(self.row());config={'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'}
        with patch.object(p,'records',return_value=[]),patch.object(a,'request',side_effect=a.IntegrationError('Timeout')):
            with self.assertRaises(a.IntegrationError):p.mirror(config,'tblDemo')
        item=p.assessment_state()['attempts'][0];self.assertIsNone(item['mirrored_id']);self.assertEqual(item['mirror_error'],'Timeout')
        item['payload']=p.canonical(item['payload']);remote={'id':'recMirror001','fields':p.attempt_fields(item)}
        with patch.object(p,'records',return_value=[remote]),patch.object(a,'request') as request:
            p.mirror(config,'tblDemo');p.mirror(config,'tblDemo');request.assert_not_called()
        self.assertEqual(p.assessment_state()['pending_mirrors'],0)
    def test_mirror_detects_source_key_collision(self):
        self.capture(self.row())
        with patch.object(p,'records',return_value=[{'id':'recBad','fields':{'Payload JSON':'changed'}}]),patch.object(a,'request') as request:
            with self.assertRaises(a.IntegrationError):p.mirror({'AIRTABLE_BASE_ID':'appTest','AIRTABLE_TOKEN':'test'},'tblDemo')
            request.assert_not_called()
    def test_quiz_graphql_errors_are_not_empty_success(self):
        with patch.object(a,'request',return_value={'errors':[{'message':'Forbidden'}]}):
            with self.assertRaises(a.IntegrationError):a.pull_native_quizzes({'THINKIFIC_API_TOKEN':'test'},[{'user_id':123}])
    def test_quiz_zero_is_preserved_and_query_scoped(self):
        item={'id':'123','quiz':{'id':'4661007'},'user':{'id':'123'},'correctCount':0,'incorrectCount':2}
        response={'data':{'site':{'quizSubmissions':{'nodes':[item],'pageInfo':{'hasNextPage':False}}}}}
        with patch.object(a,'request',return_value=response) as request:
            result=a.pull_native_quizzes({'THINKIFIC_API_TOKEN':'test'},[{'user_id':123}]);self.assertEqual(result['submissions'][0]['correctCount'],0)
            variables=request.call_args.args[3]['variables'];self.assertEqual(variables['filter']['courseIds'],['3558004']);self.assertEqual(variables['filter']['userIds'],['123'])
    def test_http_429_retries_safe_request(self):
        import urllib.error
        from email.message import Message
        headers=Message();headers['Retry-After']='1';error=urllib.error.HTTPError('https://example.test',429,'rate',headers,None)
        response=__import__('io').BytesIO(b'{"records":[]}')
        with patch('urllib.request.urlopen',side_effect=[error,response]) as req,patch.object(a.time,'sleep') as sleep:
            self.assertEqual(a.request('https://example.test','test'),{'records':[]});self.assertEqual(req.call_count,2);sleep.assert_called_once_with(1)
    def test_remote_restore_preserves_attempt_timestamp_and_detects_tampering(self):
        self.capture(self.row());item=p.assessment_state()['attempts'][0];item['payload']=p.canonical(item['payload'])
        remote={'id':'recMirrorRestore','fields':p.attempt_fields(item)}
        with p.database() as db:db.execute('DELETE FROM attempts')
        with patch.object(p,'records',return_value=[remote]):p.restore_attempts({},'tblDemo')
        restored=p.assessment_state()['attempts'][0];self.assertEqual(restored['received_at'],item['received_at']);self.assertEqual(restored['score'],0)
        self.assertEqual(restored['mirrored_id'],'recMirrorRestore')
        altered=copy.deepcopy(remote);e=json.loads(altered['fields']['Payload JSON']);e['score']=2;altered['fields']['Payload JSON']=p.canonical(e)
        with patch.object(p,'records',return_value=[altered]):
            with self.assertRaises(a.IntegrationError):p.restore_attempts({},'tblDemo')
