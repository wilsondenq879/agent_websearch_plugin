"""Input and public-network policy for the opt-in browser tool. No UI code."""
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

PRIVATE_QUERY = re.compile(r'(?:sk-|tvly-|Bearer\s+)[A-Za-z0-9_-]{12,}|(?:api[_ -]?key|password|secret|token|密碼)\s*[:=：]|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|/Users/|[A-Za-z]:\\|機密|勿外傳|confidential',re.I)

def public_url(value, resolve=True):
    if not isinstance(value, str) or len(value) > 4096 or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise ValueError('網址格式不合法。')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('只可閱讀無帳密的公開 HTTP／HTTPS 網址。')
    host = parsed.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host and ':' not in host:
        raise ValueError('不允許開啟本機或內部網路。')
    if parsed.port not in (None, 80, 443):
        raise ValueError('只允許一般網頁的 80／443 連接埠。')
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = []
        if resolve:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)]
    if any(not ip.is_global or (ip.version == 6 and ip.ipv4_mapped and not ip.ipv4_mapped.is_global) for ip in addresses):
        raise ValueError('不允許連線至私有、回環或保留位址。')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError('無效的瀏覽器工作。')
    if set(job) - {'operation', 'query', 'url', 'count', 'max_chars', 'media_type', 'focus', 'screenshot'}:
        raise ValueError('不接受任意程式碼、點擊、帳密或系統操作。')
    operation = job.get('operation')
    if operation in ('search', 'media_search'):
        query = job.get('query')
        count = job.get('count', 6)
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or re.search(r'[\x00-\x1f\x7f]', query):
            raise ValueError('搜尋詞必須是 1–500 字的單行文字。')
        if PRIVATE_QUERY.search(query):
            raise ValueError('Search keywords appear to contain private information or credentials; not submitted')
        maximum = 3 if operation == 'media_search' else 6
        if type(count) is not int or not 1 <= count <= maximum:
            raise ValueError('每次最多讀取 6 筆搜尋結果。')
        value = {'operation': operation, 'query': query.strip(), 'count': count}
        if operation == 'media_search':
            if job.get('media_type') not in ('images', 'videos'):
                raise ValueError('媒體搜尋只支援圖片或影片。')
            value['media_type'] = job['media_type']
        return value
    if operation in ('read', 'inspect'):
        limit = job.get('max_chars', 12000)
        if type(limit) is not int or not 1000 <= limit <= 20000:
            raise ValueError('正文上限必須介於 1000–20000 字元。')
        value = {'operation': operation, 'url': public_url(job.get('url')), 'max_chars': limit}
        if operation == 'inspect':
            focus = job.get('focus', '')
            screenshot = job.get('screenshot', False)
            if not isinstance(focus, str) or len(focus) > 160 or re.search(r'[\x00-\x1f]', focus) or type(screenshot) is not bool:
                raise ValueError('焦點最多 160 字，截圖須為布林值。')
            if screenshot:raise ValueError('Screenshots are not enabled in this release')
            value.update(focus=focus, screenshot=screenshot)
        return value
    raise ValueError('只開放 Google 文字／圖片／影片搜尋與公開網頁閱讀。')


def blocked_page(url, title, text):
    """Do not mistake a captcha, interstitial, or login for source material."""
    path = urlsplit(url).path
    host = urlsplit(url).hostname or ''
    if host == 'accounts.google.com' or host.endswith('.accounts.google.com'):
        return '需要登入；工具不登入帳號。'
    if path.startswith('/sorry') and host.endswith('google.com'):
        return 'Google 要求驗證碼，尚未取得搜尋結果；請由使用者接手。'
    if re.search(r'just a moment|privacy error|security check|access denied|驗證您是真人|確認你不是機器人', title, re.I):
        return '網站顯示驗證或安全攔截頁，未當成可用來源。'
    if len(text) < 7000 and re.search(r'our systems have detected unusual traffic|verify you are human|checking your browser|連線不是私人連線', text, re.I):
        return '網站要求驗證或顯示安全警告，工具未繞過。'
    if len(text) < 7000 and re.search(r'this content is only available to subscribers|subscribe to continue reading|請訂閱以繼續閱讀|您已達到免費閱讀', text, re.I):
        return '網站要求訂閱，未讀取付費內容或繞過付費牆。'
    return None
