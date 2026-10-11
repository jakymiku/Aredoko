"""Suggestion failures must leave literal and explicit search settings usable."""
import copy
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock,patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from search_intent import SearchIntent,IntentUnavailable,validate_decision,INTENTS,KINDS
from laya_process import LayaProcess
from laya_config import IDENTITY,CONTRACT,REVISION,ARTIFACTS
from production import ProductionCatalog
from production_server import production_handler,create_intent

def decision(intent='cover',kind='book'):
    return {'answers':{key:{'type':'choice','choice':chosen,
        'probabilities':{label:1.0 if label==chosen else 0.0 for label in labels}}
        for key,labels,chosen in [('intent',INTENTS,intent),('kind',KINDS,kind)]}}

class Provider:
    available=True;device='test-only'
    def __init__(self,result=None):self.result=result or decision();self.calls=0
    def decide(self,query):self.calls+=1;return self.result
    def close(self):pass

class IntentTests(unittest.TestCase):
    def test_manual_settings_survive_every_suggestion_and_no_auto_filter(self):
        for intent in INTENTS:
            for kind in KINDS:
                result=SearchIntent(Provider(decision(intent,kind))).suggest('generated','text','audio')
                self.assertEqual(result['requested'],{'source':'text','kind':'audio'})
                self.assertEqual(result['suggestion']['kind'],kind)
                self.assertFalse(result['applies_automatically'])
                self.assertFalse(result['suggestion']['scores_calibrated'])
        material=SearchIntent(Provider()).suggest('generated','cover','material')
        self.assertEqual(material['requested'],{'source':'cover','kind':'material'})

    def test_empty_disabled_and_missing_model_fallback(self):
        provider=Provider()
        self.assertEqual(SearchIntent(provider).suggest('  ')['state'],'empty')
        self.assertEqual(provider.calls,0)
        self.assertEqual(SearchIntent().suggest('generated')['state'],'disabled')
        provider.decide=MagicMock(side_effect=IntentUnavailable('missing'))
        self.assertEqual(SearchIntent(provider).suggest('generated')['state'],'unavailable')
        self.assertIsNone(SearchIntent(provider).suggest('generated')['suggestion'])

    def test_query_and_manual_settings_are_bounded(self):
        for query in (None,{},'a'*301,'x\0y'):
            with self.assertRaises(ValueError):SearchIntent().suggest(query)
        with self.assertRaises(ValueError):SearchIntent().suggest('x',source='auto')
        with self.assertRaises(ValueError):SearchIntent().suggest('x',kind='unknown')

    def test_bad_or_truncated_outputs_fallback_instead_of_misleading_suggestion(self):
        malformed=[[],{}, {'answers':{}}, {**decision(),'usage':{'truncated':True}}]
        for field,value in [('choice','unknown'),('probabilities',{'cover':1.0}),('probabilities',{'cover':float('nan'),'text':0.0,'mixed':0.0}),
                            ('probabilities',{'cover':True,'text':0.0,'mixed':0.0}),('probabilities',{'cover':0.0,'text':1.0,'mixed':0.0})]:
            row=decision();row['answers']['intent'][field]=value;malformed.append(row)
        for result in malformed:
            provider=Provider();provider.result=result
            with self.subTest(result=result):self.assertEqual(SearchIntent(provider).suggest('generated')['state'],'unavailable')

    def test_probability_rounding_is_tolerated_without_confidence_threshold(self):
        result=decision();result['answers']['intent']={'type':'choice','choice':'mixed',
            'probabilities':{'cover':0.3333,'text':0.3333,'mixed':0.3334}}
        self.assertEqual(validate_decision(result)['intent']['choice'],'mixed')

    def test_worker_queue_rejects_non_objects_and_times_out(self):
        p=LayaProcess('missing','missing',warm_timeout=0.01)
        with self.assertRaises(IntentUnavailable):p._response(0.01)
        p.responses.put([])
        with self.assertRaises(IntentUnavailable):p._response(0.01)
        process=MagicMock();process.stdout.readline.side_effect=['[]\n','']
        responses=queue.Queue(maxsize=2);p._read(process,responses)
        self.assertIn('error',responses.get())

    def test_busy_worker_falls_back_without_queued_work_and_close_is_terminal(self):
        p=LayaProcess('missing','missing')
        p.lock.acquire()
        try:
            with self.assertRaises(IntentUnavailable):p.decide('generated')
        finally:p.lock.release()
        p.close();self.assertFalse(p.available)
        with self.assertRaises(IntentUnavailable):p.decide('generated')

    def test_incompatible_hello_and_disconnect_kill_owned_worker(self):
        for hello in ({'ready':True,'identity':{},'contract':CONTRACT,'device':'cpu'},
                      {'ready':False,'identity':IDENTITY,'contract':CONTRACT,'device':'cpu'}):
            p=LayaProcess('fake-python','fake-model')
            process=MagicMock();process.poll.return_value=None
            with patch.object(LayaProcess,'available',new_callable=lambda:property(lambda self:True)),                 patch('laya_process.subprocess.Popen',return_value=process),                 patch('laya_process.threading.Thread'),patch.object(p,'_response',return_value=hello):
                self.assertEqual(SearchIntent(p).suggest('generated')['state'],'unavailable')
                process.kill.assert_called_once();self.assertIsNone(p.process)
                self.assertGreater(p.retry_after,0)

    def test_wrong_revision_or_source_is_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp);python=model/'python.exe';python.touch()
            for name in ARTIFACTS:
                p=model/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
            marker=model/'aredoko-revision.txt';marker.write_text(REVISION)
            source=model/'aredoko-source.json';source.write_text(json.dumps(IDENTITY))
            provider=LayaProcess(python,model);self.assertTrue(provider.available)
            marker.write_text('a'*40);self.assertFalse(provider.available)
            marker.write_text(REVISION);source.write_text('{}');self.assertFalse(provider.available)
            source.write_text(json.dumps(IDENTITY));marker.write_text('x'*129);self.assertFalse(provider.available)
            marker.write_text(REVISION);source.write_text(' '*8193);self.assertFalse(provider.available)

    def test_frozen_fixture_has_36_requests_and_separate_held_out_subset(self):
        rows=json.loads((Path(__file__).parent/'fixtures/laya-ja-queries.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows),36);self.assertEqual(sum(r['split']=='held-out' for r in rows),12)
        self.assertEqual(len({r['query'] for r in rows}),36)
        self.assertTrue(all(r['intent'] in INTENTS and r['kind'] in KINDS for r in rows))

    def test_http_token_origin_and_fallback_do_not_break_literal_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog=ProductionCatalog(Path(tmp)/'catalog.sqlite')
            provider=Provider();provider.decide=MagicMock(side_effect=IntentUnavailable('timeout'))
            server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,'fixture-token',intent=SearchIntent(provider)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                headers={'X-Aredoko-Token':'fixture-token','Origin':url,'Content-Type':'application/json'}
                request=urllib.request.Request(url+'/api/library/intent/suggest',b'{"query":"generated","source":"text","kind":"audio"}',headers)
                with urllib.request.urlopen(request) as response:
                    result=json.load(response);self.assertEqual(result['state'],'unavailable')
                    self.assertEqual(result['requested'],{'source':'text','kind':'audio'})
                self.assertEqual(catalog.search()['total'],0)
                headers.pop('Origin')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url+'/api/library/intent/suggest',b'{"query":"generated"}',headers))
                self.assertEqual(error.exception.code,403);error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url+'/api/library/intent/status')
                self.assertEqual(error.exception.code,403);error.exception.close()
            finally:server.shutdown();server.server_close();catalog.close()
        self.assertFalse(create_intent().status()['enabled'])
