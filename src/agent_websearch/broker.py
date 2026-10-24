"""Authenticated loopback broker for the explicitly approved, manual Edge tool.

No browser profile access, shell execution, model scripts or remote listeners.
The extension credential can consume jobs, but cannot create them.
"""
from __future__ import annotations

import hmac
import json
import re
import threading
import time
import uuid
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import policy as POLICY
from . import media as MEDIA
from . import research as RESEARCH
PRIVATE_HOSTS = {'accounts.google.com', 'mail.google.com', 'drive.google.com', 'docs.google.com',
    'outlook.live.com', 'outlook.office.com', 'outlook.office365.com', 'teams.microsoft.com',
    'login.microsoftonline.com', 'login.live.com', 'account.microsoft.com'}


def edge_url(value):
    from urllib.parse import urlsplit
    url = POLICY.public_url(value)
    parsed = urlsplit(url)
    if parsed.hostname in PRIVATE_HOSTS or re.search(r'/(?:login|signin|sign-in|account|settings)(?:/|$)', parsed.path, re.I):
        raise ValueError('此工具只閱讀公開來源，不開啟帳戶、郵件或管理頁面。')
    return url


def clean_result(payload, value):
    if not isinstance(value, dict):
        raise ValueError('Invalid extension result')
    if value.get('status') != 'ok':
        return {'status': 'human_required' if value.get('status') == 'human_required' else 'error',
            'message': str(value.get('message', 'Edge 未取得可用內容。'))[:500], 'results_verified': False}
    url = edge_url(value.get('url'))
    title = str(value.get('title', ''))[:300]
    text = str(value.get('text', ''))[:22000]
    reason = POLICY.blocked_page(url, title, text)
    if reason:
        return {'status': 'human_required', 'message': reason, 'results_verified': False}
    result = {'status': 'ok', 'backend': 'browser_bridge', 'url': url, 'title': title}
    if payload['operation'] == 'search':
        items = []
        for item in value.get('results', [])[:payload['count']]:
            if not isinstance(item, dict):
                continue
            try:
                target = edge_url(item.get('url'))
            except (ValueError, OSError):
                continue
            items.append({'title': str(item.get('title', ''))[:300], 'url': target,
                'snippet': str(item.get('snippet', ''))[:1200], 'page_read': False})
        if not items:
            raise ValueError('Edge 頁面沒有可驗證的公開搜尋結果。')
        result.update(results=items, results_verified=True, query=payload['query'])
    elif payload['operation'] == 'media_search':
        items = MEDIA.clean_items(value.get('results'), payload['media_type'], payload['count'], edge_url)
        if not items:
            return {**result, 'status': 'empty', 'media_type': payload['media_type'], 'results': [],
                    'results_verified': False, 'message': '沒有取得可核對來源的媒體結果。'}
        result.update(results=items, media_type=payload['media_type'], results_verified=True, query=payload['query'])
    else:
        if len(text.strip()) < 80:
            raise ValueError('網頁正文不足，未當成已閱讀來源。')
        limit = payload['max_chars']
        result.update(text=text[:limit], truncated=bool(value.get('truncated')) or len(text) > limit,
            page_read=True, results_verified=True)
        result['evidence'] = RESEARCH.normalize({**value, 'url': url, 'text':text[:limit]}, edge_url)
    return result


class Broker:
    def __init__(self, server_token, worker_token):
        self.server_token, self.worker_token = server_token, worker_token
        self.condition = threading.Condition()
        self.jobs = {}
        self.last_seen = 0
        self.paused = False
        self.max_results = 5  # Backward-compatible old extension capacity.
        self.media_supported = False
        self.research_supported = False

    def state(self):
        age = time.monotonic() - self.last_seen
        return {'protocol_version':1,'connected': self.last_seen > 0 and age < 50, 'paused': self.paused,
            'backend': 'browser_bridge', 'pending': len(self.jobs), 'max_results': self.max_results,
            'media_supported': self.media_supported, 'research_supported': self.research_supported}

    def run(self, value, timeout=48, identifier=None):
        payload = POLICY.validate_job(value)
        if payload['operation'] in ('read','inspect'):
            payload['url'] = edge_url(payload['url'])
        with self.condition:
            state = self.state()
            if not state['connected'] or state['paused']:
                raise ValueError('Edge 橋接未連線或已暫停；請開啟 Edge 並檢查擴充功能。')
            if payload['operation'] == 'search' and payload['count'] > self.max_results:
                raise ValueError('請重新載入 Agent Websearch Bridge，以支援 6 筆結果。')
            if payload['operation'] == 'media_search' and not self.media_supported:
                raise ValueError('請重新載入 Agent Websearch Bridge，啟用圖片與影片搜尋。')
            if payload['operation'] == 'inspect' and not self.research_supported:
                raise ValueError('請重新載入 Agent Websearch Bridge，啟用表格與證據擷取。')
            if self.jobs:
                raise ValueError('Edge 正在執行另一個瀏覽器工作，請稍後再試。')
            identifier = identifier or uuid.uuid4().hex
            if not re.fullmatch('[0-9a-f]{32}', identifier):
                raise ValueError('Invalid job ID')
            entry = {'id': identifier, 'payload': payload, 'deadline': time.monotonic() + timeout,
                'expires_at': int((time.time() + timeout) * 1000), 'leased': False, 'result': None}
            self.jobs[identifier] = entry
            self.condition.notify_all()
            try:
                while entry['result'] is None:
                    remaining = entry['deadline'] - time.monotonic()
                    if remaining <= 0:
                        raise ValueError('Edge 工作逾時，未宣稱有搜尋結果。')
                    self.condition.wait(remaining)
                return clean_result(payload, entry['result'])
            finally:
                self.jobs.pop(identifier, None)
                self.condition.notify_all()

    def next(self, paused=False, timeout=18, max_results=5, media_supported=False, research_supported=False):
        deadline = time.monotonic() + timeout
        with self.condition:
            self.last_seen, self.paused = time.monotonic(), paused
            self.max_results = max_results if type(max_results) is int and 1 <= max_results <= 6 else 5
            self.media_supported = bool(media_supported)
            self.research_supported = bool(research_supported)
            while not paused:
                for entry in self.jobs.values():
                    if not entry['leased'] and entry['deadline'] > time.monotonic():
                        entry['leased'] = True
                        return {key: entry[key] for key in ('id', 'payload', 'expires_at')}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            self.last_seen = time.monotonic()
            return None

    def finish(self, value):
        if not isinstance(value, dict) or not re.fullmatch('[0-9a-f]{32}', str(value.get('id', ''))):
            raise ValueError('Invalid job ID')
        with self.condition:
            entry = self.jobs.get(value['id'])
            if not entry or not entry['leased'] or entry['result'] is not None:
                raise ValueError('工作已結束或不是已派發的工作。')
            entry['result'] = value.get('result')
            self.last_seen = time.monotonic()
            self.condition.notify_all()

    def cancel(self, identifier):
        with self.condition:
            entry = self.jobs.get(identifier)
            if entry:
                entry['result'] = {'status': 'error', 'message': '使用者已取消工作。'}
                self.condition.notify_all()

    def active(self, identifier):
        with self.condition:
            entry = self.jobs.get(identifier)
            return bool(entry and entry['result'] is None and entry['deadline'] > time.monotonic())


def handler_for(broker, port):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'AgentWebsearch/0.1'

        def log_message(self, *_):
            pass  # Never log query text, URLs, credentials or page content.

        def allowed(self, role):
            if self.headers.get('Host') != '127.0.0.1:' + str(port):
                return False
            origin = self.headers.get('Origin', '')
            if origin and not re.fullmatch(r'chrome-extension://[a-p]{32}', origin):
                return False
            expected = broker.server_token if role == 'server' else broker.worker_token
            supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
            return hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))

        def respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            role = 'worker' if self.path.startswith('/bridge/') else 'server'
            if not self.allowed(role):
                return self.respond(403, {'error': 'Forbidden'})
            if self.path in ('/api/health', '/bridge/health'):
                return self.respond(200, broker.state())
            parsed = urlsplit(self.path)
            if parsed.path == '/bridge/next':
                query = parse_qs(parsed.query)
                max_results = 6 if query.get('max_count') == ['6'] else 5
                return self.respond(200, {'job': broker.next(paused=query.get('paused') == ['1'], max_results=max_results,
                    media_supported=query.get('media') == ['1'], research_supported=query.get('research') == ['1'])})
            if self.path.startswith('/bridge/active/'):
                return self.respond(200, {'active': broker.active(self.path.rsplit('/', 1)[-1])})
            self.respond(404, {'error': 'Not found'})

        def do_POST(self):
            role = 'worker' if self.path == '/bridge/result' else 'server'
            if not self.allowed(role):
                return self.respond(403, {'error': 'Forbidden'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                maximum = 1800000 if self.path == '/bridge/result' else 150000
                if not 0 < length <= maximum or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid JSON body')
                self.connection.settimeout(5)
                value = json.loads(self.rfile.read(length))
                if self.path == '/api/run':
                    return self.respond(200, broker.run(value['payload'], identifier=value['id']))
                if self.path == '/api/cancel':
                    broker.cancel(value.get('id'))
                    return self.respond(200, {'ok': True})
                if self.path == '/bridge/result':
                    broker.finish(value)
                    return self.respond(200, {'ok': True})
                self.respond(404, {'error': 'Not found'})
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.respond(400, {'status': 'error', 'message': str(error)[:500], 'results_verified': False})

    return Handler


def make_server(config):
    """Loopback only. Port 0 is reserved for isolated test instances."""
    broker = Broker(config['server_token'], config['worker_token'])
    server = ThreadingHTTPServer(('127.0.0.1', config['port']), BaseHTTPRequestHandler)
    server.RequestHandlerClass = handler_for(broker, server.server_port)
    server.daemon_threads = True
    server.broker = broker
    return server
