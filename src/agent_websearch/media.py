"""Bounded image/video references with validated public source attribution."""
import base64
import re
from urllib.parse import urlsplit, parse_qs


def thumbnail(value, public_url):
    if not isinstance(value, str):
        return None
    if value.startswith('data:'):
        match = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', value)
        if not match or len(value) > 40000:
            return None
        try:
            data = base64.b64decode(match[2], validate=True)
        except ValueError:
            return None
        valid = (data.startswith(b'\xff\xd8\xff') if match[1] == 'jpeg' else
                 data.startswith(b'\x89PNG\r\n\x1a\n') if match[1] == 'png' else
                 data.startswith(b'RIFF') and data[8:12] == b'WEBP')
        return value if valid else None
    try:
        return public_url(value)
    except (ValueError, OSError):
        return None


def video_id(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower().removeprefix('www.')
        if host == 'youtu.be':
            identifier = url.path.strip('/')
        elif host in ('youtube.com', 'm.youtube.com'):
            identifier = (parse_qs(url.query).get('v') or [''])[0] if url.path == '/watch' else url.path.split('/')[-1] if url.path.startswith(('/shorts/', '/embed/')) else ''
        else:
            return None
        return identifier if re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier) else None
    except (TypeError, ValueError):
        return None


def clean_items(raw, kind, count, public_url):
    items, seen = [], set()
    for item in (raw if isinstance(raw, list) else [])[:24]:
        if not isinstance(item, dict):
            continue
        try:
            source = public_url(item.get('url'))
            host = (urlsplit(source).hostname or '').lower()
            if host == 'google.com' or host.endswith('.google.com'):
                continue
        except (ValueError, TypeError, OSError):
            continue
        if source in seen:
            continue
        title = re.sub(r'[\x00-\x1f\x7f]', ' ', str(item.get('title') or '')).strip()[:180]
        if not title:
            continue
        thumb = thumbnail(item.get('thumbnail_url'), public_url)
        if kind == 'images' and not thumb:
            continue
        entry = {'title': title, 'url': source, 'thumbnail_url': thumb, 'source_host': host,
                 'page_read': False, 'media_type': kind}
        if kind == 'videos':
            identifier = video_id(source)
            if identifier:
                entry.update(url='https://www.youtube.com/watch?v=' + identifier,
                             video_id=identifier, embed_available='try_on_user_click')
            else:
                entry['embed_available'] = False
        seen.add(source)
        items.append(entry)
        if len(items) >= count:
            break
    return items
