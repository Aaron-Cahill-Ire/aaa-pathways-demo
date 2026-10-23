import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hosted',ROOT/'api/dashboard.py')
hosted=importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)

class HostedTests(unittest.TestCase):
    def setUp(self):
        hosted.CACHE=None
        hosted.CACHE_AT=0

    def test_no_credentials_shows_real_populated_capture_without_api_call(self):
        with patch.dict(os.environ,{},clear=True),patch.object(hosted,'read_live') as live:
            result=hosted.dashboard()
        live.assert_not_called()
        self.assertEqual(result['hosted_mode'],'snapshot')
        self.assertEqual(len(result['people']),6)
        self.assertEqual(len(result['assessments']['attempts']),6)
        self.assertTrue(all(p['email'].endswith('@example.test') for p in result['people']))
        self.assertEqual(result['people'][0]['percent'],0)
        self.assertTrue(result['read_only'])

    def test_live_cache_and_error_fallback_never_expose_provider_secrets(self):
        with patch.dict(os.environ,{k:'private-value' for k in hosted.REQUIRED},clear=True):
            fresh=hosted.baseline();fresh['hosted_mode']='live'
            with patch.object(hosted,'read_live',return_value=fresh) as live:
                result=hosted.dashboard();result['people'].clear()
                again=hosted.dashboard(force=True)
                self.assertEqual(len(again['people']),6)
                live.assert_called_once()
            hosted.CACHE_AT=0
            with patch.object(hosted,'read_live',side_effect=RuntimeError('private-value')):
                stale=hosted.dashboard(force=True)
            self.assertEqual(stale['hosted_mode'],'stale')
            self.assertNotIn('private-value',json.dumps(stale))
            self.assertEqual(stale['airtable']['state'],'error')
            self.assertEqual(stale['people'][0]['progress_source'],'Thinkific last verified snapshot; stale')

    def test_live_reads_remote_attempts_and_never_calls_vendor_writes(self):
        baseline=hosted.baseline()
        profiles=copy.deepcopy(baseline['people'])
        for p in profiles:p.pop('attempts',None)
        # Generate mirror envelopes using the same validated contract as Airtable.
        remote=[]
        for index,attempt in enumerate(baseline['assessments']['attempts']):
            encoded={**attempt,'payload':json.dumps(attempt['payload'])}
            remote.append({'id':attempt['mirrored_id'] or 'recMirror'+str(index),'fields':hosted.pipeline.attempt_fields(encoded)})
        prior=hosted.pipeline.DB
        with patch.object(hosted.sources,'pull_airtable',return_value=(profiles,'tblDemo','appDemo')), \
             patch.object(hosted.sources,'pull_thinkific',return_value=baseline['thinkific_data']), \
             patch.object(hosted.sources,'airtable_config',return_value={'AIRTABLE_TOKEN':'unused','AIRTABLE_BASE_ID':'appDemo'}), \
             patch.object(hosted.pipeline,'table_ids',return_value=('tblDemo','tblAttempts')), \
             patch.object(hosted.pipeline,'records',side_effect=[remote,[]]) as reads, \
             patch.object(hosted.sources,'request',side_effect=AssertionError('Unexpected vendor request')), \
             patch.object(hosted.sources,'sync',side_effect=AssertionError('No sync allowed')), \
             patch.object(hosted.pipeline,'mirror',side_effect=AssertionError('No mirrors allowed')):
            result=hosted.read_live()
        self.assertEqual(result['hosted_mode'],'live')
        self.assertEqual(len(result['assessments']['attempts']),6)
        self.assertEqual(result['assessments']['pending_mirrors'],0)
        self.assertEqual(result['people'][0]['percent'],0)
        self.assertEqual(hosted.pipeline.DB,prior)
        self.assertEqual(reads.call_count,2)

    def test_changed_identity_stops_before_thinkific_or_attempt_read(self):
        people=hosted.baseline()['people'];people[0]['email']='someone@example.test'
        with patch.object(hosted.sources,'pull_airtable',return_value=(people,'tbl','app')),patch.object(hosted.sources,'pull_thinkific') as tf:
            with self.assertRaises(hosted.sources.IntegrationError):hosted.read_live()
        tf.assert_not_called()

if __name__=='__main__':unittest.main()
