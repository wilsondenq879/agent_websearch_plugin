"""Bounded evidence normalization and source-only chart data. No model code."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from urllib.parse import urlsplit


def clean(value, limit=500):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(value or '')).strip()[:limit]


def checked_at():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def safe_url(value, public_url):
    url = public_url(value)
    parsed = urlsplit(url)
    if parsed.hostname in {'accounts.google.com', 'mail.google.com', 'drive.google.com', 'docs.google.com', 'teams.microsoft.com', 'outlook.office.com', 'outlook.live.com', 'login.microsoftonline.com', 'login.live.com'} or re.search(r'/(login|signin|sign-in|account|settings)(/|$)', parsed.path, re.I):
        raise ValueError('只開放公開資料，不讀取帳戶或管理頁面。')
    return url


def tables(raw):
    output, budget = [], 6000
    for table in (raw if isinstance(raw, list) else [])[:10]:
        rows = table.get('rows') if isinstance(table, dict) else None
        if not isinstance(rows, list):
            continue
        bounded = []
        for row in rows[:41]:
            if not isinstance(row,list): continue
            cells = [clean(cell, 120) for cell in row[:12]]
            size = sum(map(len,cells))
            if size > budget: break
            budget -= size; bounded.append(cells)
        rows = bounded
        if len(rows) < 2 or not 2 <= len(rows[0]) <= 12:
            continue
        rectangular = len({len(r) for r in rows}) == 1 and all(isinstance(row,list) and len(row) <= 12 and all(len(clean(cell,10000)) <= 120 for cell in row) for row in table['rows'])
        output.append({'index': len(output), 'caption': clean(table.get('caption'), 200),
            'rows': rows, 'page': table.get('page') if type(table.get('page')) is int else None,
            'chart_eligible': rectangular and not table.get('complex', False),
            'truncated': bool(table.get('truncated')) or len(rows)<len(table['rows']), 'warning': '' if rectangular and not table.get('complex') else '合併儲存格或列寬不一致，不能直接製圖'})
    return output


def normalize(raw, public_url, focus=''):
    result = {'title': clean(raw.get('title'), 300), 'url': safe_url(raw.get('url'), public_url),
        'checked_at': checked_at(), 'publication_date': clean(raw.get('publication_date'), 80) or None,
        'modified_date': clean(raw.get('modified_date'), 80) or None,
        'date_notice': '查閱日期不是發表日期；頁面日期未經獨立驗證。',
        'tables': tables(raw.get('tables')), 'page_read': True}
    excerpts = []
    for quote in raw.get('excerpts', [])[:4]:
        quote = clean(quote, 700)
        if quote and quote in raw.get('text', ''):
            excerpts.append(quote)
    result['excerpts'] = excerpts
    links = []
    for link in raw.get('document_links', [])[:8]:
        try:
            links.append({'title': clean(link.get('title'), 180), 'url': safe_url(link.get('url'), public_url)})
        except (ValueError, OSError, TypeError):
            pass
    result['document_links'] = links
    reviews = [clean(r, 400) for r in raw.get('reviews', [])[:3] if clean(r)]
    result['reviews'] = {'visible_samples': reviews, 'count': len(reviews),
        'notice': '僅目前公開頁面可見樣本，不代表整體用戶、普遍故障率或已驗證事實；未作情緒模型評分。'}
    result['interpretation_rules'] = '原文是來源的主張，不等於獨立證實；規格、售價與評論須分開。比較數值須核對地區、日期、幣別、單位與統計母體。'
    return result


def remember(state, result):
    if result.get('status') != 'ok' or not result.get('page_read'):
        return
    content = {'url': result['url'], 'title': result.get('title'), 'text': result.get('text', ''),
        'evidence': result.get('evidence') or {}, 'pages': result.get('pages') or []}
    key = 'ev-' + hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    sources = getattr(state, 'research_sources', {})
    if len(sources) >= 10 and key not in sources:
        sources.pop(next(iter(sources)))
    sources[key] = content
    state.research_sources = sources
    result['evidence_id'] = key


def numeric(cell, unit):
    """No imputation, magnitude/currency conversion, ranges or estimated input."""
    raw = clean(cell, 120).replace('\u00a0', ' ').replace('−', '-')
    match = re.fullmatch(r'(?P<prefix>NT\$|US\$|USD|TWD|EUR|JPY|HKD|\$|€|¥)?\s*(?P<value>[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(?P<suffix>[%A-Za-z/\u3400-\u9fff²³]+)?', raw)
    if not match:
        raise ValueError('儲存格不是可直接引用的單一數值：' + raw[:60])
    prefix, suffix = match['prefix'] or '', match['suffix'] or ''
    currency = {'NT$': 'TWD', 'US$': 'USD', '€': 'EUR', '¥': 'JPY'}
    expected = currency.get(unit, unit).strip().lower()
    for value in (prefix, suffix):
        actual = currency.get(value, value).strip().lower()
        if actual and actual != expected:
            raise ValueError('幣別／單位不一致；不自動換算或猜測：' + raw[:60])
    # A bare number is usable only with an independently checked header unit.
    number = float(match['value'].replace(',', ''))
    if not math.isfinite(number):
        raise ValueError('數值超過可繪製範圍。')
    return number


def chart_payload(source, table_index, label_column, value_column, unit, row_start=0, row_count=12, chart_type='auto'):
    evidence = source.get('evidence') or {}
    ts = evidence.get('tables') or []
    if type(table_index) is not int or not 0 <= table_index < len(ts):
        raise ValueError('此證據沒有指定的表格。')
    table = ts[table_index]
    if not table.get('chart_eligible'):
        raise ValueError('此表有合併欄位或不規則資料，請先人工核對，未繪圖。')
    rows = table['rows']
    if any(type(v) is not int or not 0 <= v < len(rows[0]) for v in (label_column, value_column)) or label_column == value_column:
        raise ValueError('請提供不同且存在的標籤／數值欄索引（從 0 開始）。')
    if type(row_start) is not int or row_start < 0 or type(row_count) is not int or not 2 <= row_count <= 12:
        raise ValueError('一次製圖 2–12 列，row_start 從 0 開始。')
    if chart_type not in ('auto', 'bar', 'horizontal_bar', 'line'):
        raise ValueError('來源表格先支援長條、橫條與折線；不把任意資料當成佔比。')
    unit = clean(unit, 30)
    if not unit:
        raise ValueError('必須指定來源中可核對的單位。')
    header = rows[0][value_column]
    scales = re.findall(r'百萬|百万|million|billion|thousand|千|萬|万|億|亿',header,re.I)
    if any(scale.casefold() not in unit.casefold() for scale in scales):
        raise ValueError('欄名含數量級，指定單位不可省略或自行換算。')
    chosen = rows[1:][row_start:row_start + row_count]
    if len(chosen) < 2:
        raise ValueError('可比較資料不足兩筆。')
    # Require the supplied unit in the column header or every numeric cell.
    # Never let the model relabel unitless market/price values arbitrarily.
    aliases = {'TWD': ('NT$', 'TWD', '新臺幣', '新台幣'), 'USD': ('US$', 'USD', '美元'), '%': ('%', '百分比')}
    names = aliases.get(unit.upper(), (unit,))
    header_unit = any(name.casefold() in header.casefold() for name in names)
    if not header_unit and not all(any(name.casefold() in row[value_column].casefold() for name in names) for row in chosen):
        raise ValueError('無法從欄名或每個儲存格核對單位；未繪圖。')
    labels = [row[label_column] for row in chosen]
    if any(not value for value in labels) or len(set(labels)) != len(labels):
        raise ValueError('標籤缺失或重複，無法直接製圖。')
    values = [numeric(row[value_column], unit) for row in chosen]
    note = f'引用原表第 {row_start + 1}–{row_start + len(chosen)} 列；未補值、換算、推估或驗證來源測量方法。'
    if table.get('page'):
        note += f" PDF 第 {table['page']} 頁。"
    return {'title': clean(table.get('caption') or source.get('title') or '來源數據比較', 100),
        'labels': labels, 'series': [{'name': header, 'values': values}], 'unit': unit,
        'data_kind': 'reported', 'chart_type': chart_type, 'sources': [source['url'] + ' 查閱 ' + str(evidence.get('checked_at') or checked_at())[:10]],
        'note': note, 'better': 'neutral'}
