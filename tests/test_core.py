import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from agent_websearch import Client
from agent_websearch import broker,policy
from agent_websearch.config import init,load


class ConfigTests(unittest.TestCase):
    def test_fresh_private_setup_is_idempotent_and_bundles_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=init(root,18769);before=(root/'config.json').read_bytes()
            init(root,18769)
            self.assertEqual(before,(root/'config.json').read_bytes())
            config=load(root/'config.json')
            self.assertNotEqual(config['server_token'],config['worker_token'])
            self.assertNotIn(config['worker_token'],json.dumps(first))
            manifest=json.loads((root/'extension/manifest.json').read_text())
            self.assertEqual(manifest['version'],'0.1.0')
            self.assertIn('127.0.0.1:18769',manifest['content_security_policy']['extension_pages'])
            self.assertIn(config['worker_token'],(root/'extension/runtime-config.js').read_text())
            if os.name=='posix':self.assertEqual((root/'config.json').stat().st_mode&0o777,0o600)
            with self.assertRaises(ValueError):init(root,18770)

    def test_invalid_config_and_query_data_fail_closed(self):
        for payload in [{'operation':'shell','command':'id'}, {'operation':'search','query':'x','count':True},
                        {'operation':'search','query':'password=private'}, {'operation':'search','query':'a@example.org'},
                        {'operation':'inspect','url':'https://8.8.8.8/public','max_chars':7000,'focus':'','screenshot':True}]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):policy.validate_job(payload)
        for url in ['file:///etc/passwd','http://localhost','http://127.0.0.1','http://[::1]',
                    'http://10.0.0.1','https://example.org:9222','https://user:pass@example.org','http://host.internal']:
            with self.assertRaises(ValueError):policy.public_url(url,resolve=False)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):policy.public_url('https://public-looking.test')


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        init(self.root,18769);self.config=load(self.root/'config.json')
        self.server=broker.make_server(self.config|{'port':0})
        self.config['port']=self.server.server_port
        (self.root/'config.json').write_text(json.dumps(self.config))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        original=policy.public_url
        self.urls=patch.object(policy,'public_url',side_effect=lambda url:original(url,resolve=False));self.urls.start()
        self.client=Client(self.root/'config.json')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.urls.stop();self.temp.cleanup()

    def worker_reply(self,payload):
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.client.run,payload)
            job=self.server.broker.next(timeout=2,max_results=6,media_supported=True,research_supported=True)
            self.assertIsNotNone(job)
            self.assertIsNone(self.server.broker.next(timeout=0,max_results=6))
            value={'status':'ok','url':'https://example.org/source','title':'Public source','text':'Real visible source body. '*30,
                   'results':[{'title':'Public result','url':'https://example.org/source','snippet':'A real snippet'}]}
            self.server.broker.finish({'id':job['id'],'result':value})
            return future.result(timeout=3)

    def test_actual_http_client_search_and_read_contract(self):
        self.assertEqual(self.client.status()['protocol_version'],1)
        self.assertFalse(self.client.status()['connected'])
        self.server.broker.next(timeout=0,max_results=6)
        search=self.worker_reply({'operation':'search','query':'public test','count':6})
        self.assertEqual(search['backend'],'browser_bridge')
        self.assertTrue(search['results_verified']);self.assertFalse(search['results'][0]['page_read'])
        self.assertEqual(len(search['results']),1,'Never pad results to the requested count')
        read=self.worker_reply({'operation':'read','url':'https://example.org/source','max_chars':7000})
        self.assertTrue(read['page_read']);self.assertIn('Real visible',read['text'])
        self.assertEqual(self.server.broker.state()['pending'],0)

    def test_role_separation_bad_origins_and_host_headers(self):
        handler=broker.handler_for(self.server.broker,self.server.server_port)
        fake=object.__new__(handler)
        base={'Host':'127.0.0.1:'+str(self.server.server_port),'Authorization':'Bearer '+self.config['worker_token']}
        for changed,role,expected in [({},'worker',True),({},'server',False),
             ({'Origin':'https://evil.example'},'worker',False),({'Host':'attacker.test'},'worker',False)]:
            fake.headers=base|changed;self.assertEqual(fake.allowed(role),expected)
        # A public HTTP request with no credential must be rejected, not just
        # a unit-level comparison of secrets.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with self.assertRaises(urllib.error.HTTPError) as error:
            opener.open('http://127.0.0.1:'+str(self.server.server_port)+'/api/health',timeout=2)
        self.assertEqual(error.exception.code,403)

    def test_media_attribution_and_visible_evidence(self):
        result=broker.clean_result({'operation':'media_search','media_type':'videos','count':2,'query':'public video'},
            {'status':'ok','url':'https://www.google.com/search?q=public','title':'Search','results':[
                {'title':'Public video','url':'https://youtu.be/abcdefghijk'},
                {'title':'Private target','url':'http://127.0.0.1/internal'}]})
        self.assertEqual(len(result['results']),1)
        self.assertEqual(result['results'][0]['url'],'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertFalse(result['results'][0]['page_read'])
        page=broker.clean_result({'operation':'inspect','max_chars':7000},
            {'status':'ok','url':'https://example.org/source','title':'Public source','text':'Visible public evidence. '*20,
             'tables':[{'rows':[['Label','Count'],['A','10'],['B','20']]}],
             'excerpts':['Visible public evidence.','Invented quote'], 'publication_date':'2026-10-01'})
        self.assertTrue(page['page_read'])
        self.assertEqual(page['evidence']['excerpts'],['Visible public evidence.'])
        self.assertEqual(page['evidence']['publication_date'],'2026-10-01')
        self.assertTrue(page['evidence']['checked_at'].endswith('+00:00'))
        self.assertTrue(page['evidence']['tables'][0]['chart_eligible'])

    def test_pause_busy_cancellation_and_captcha(self):
        self.server.broker.next(paused=True,timeout=0,max_results=6)
        self.assertEqual(self.client.search('public test')['status'],'error')
        self.server.broker.next(paused=False,timeout=0,max_results=6)
        identifier='a'*32
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.client._request,'/api/run',{'id':identifier,'payload':{'operation':'search','query':'public','count':1}})
            self.assertIsNotNone(self.server.broker.next(timeout=2,max_results=6))
            self.assertEqual(self.client.search('other query')['status'],'error')
            self.client._request('/api/cancel',{'id':identifier})
            self.assertEqual(future.result(timeout=3)['status'],'error')
        result=broker.clean_result({'operation':'search','count':1},
                                   {'status':'human_required','message':'captcha'})
        self.assertEqual(result['status'],'human_required');self.assertFalse(result['results_verified'])


if __name__=='__main__':unittest.main()
