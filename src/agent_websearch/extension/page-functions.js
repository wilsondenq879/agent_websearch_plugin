/* Static, self-contained injection functions. Never accept executable code. */
function inspectPage(maxChars, searchCount) {
  const visible = el => !!(el && el.getClientRects().length);
  const body = document.body?.innerText || '';
  const root = document.querySelector('article, main, [role="main"]') || document.body;
  const text = root?.innerText || body;
  const result = {url: location.href, title: document.title, text: text.slice(0, maxChars),
    truncated: text.length > maxChars, results: []};
  if (searchCount) {
    const seen = new Set();
    for (const heading of document.querySelectorAll('a h3')) {
      if (!visible(heading)) continue;
      const anchor = heading.closest('a');
      const url = anchor?.href;
      if (!url || !/^https?:/.test(url) || seen.has(url)) continue;
      try {
        const host = new URL(url).hostname;
        if (/(^|\.)google\.[a-z.]+$/.test(host)) continue;
      } catch { continue; }
      seen.add(url);
      // Keep just the result card, not the whole results page/account header.
      let card = anchor;
      for (let i = 0; i < 4 && card.parentElement; i++) {
        if (card.innerText.length > heading.innerText.length + 100) break;
        card = card.parentElement;
      }
      result.results.push({title: heading.innerText, url,
        snippet: card.innerText.slice(0, 1200), page_read: false});
      if (result.results.length >= searchCount) break;
    }
  }
  return result;
}

function inspectEvidence(maxChars, focus) {
  const visible = el => !!el?.getClientRects().length;
  const root = document.querySelector('article, main, [role="main"]') || document.body;
  const text = (root?.innerText || '').slice(0, maxChars);
  const terms = String(focus || '').toLowerCase().match(/[a-z0-9-]{2,}|[\u3400-\u9fff]{2,}/g) || [];
  const paragraphs = text.split(/\n+/).map(p => p.trim()).filter(p => p.length >= 30 && p.length <= 700);
  const excerpts = paragraphs.filter(p => !terms.length || terms.some(t => p.toLowerCase().includes(t))).slice(0, 3);
  const tables = [];
  for (const table of root?.querySelectorAll('table') || []) {
    if (!visible(table) || tables.length >= 8) continue;
    const trs = [...table.querySelectorAll('tr')].filter(visible);
    const rows = trs.slice(0, 41).map(tr => [...tr.cells].filter(visible).slice(0, 12).map(c => c.innerText.trim().slice(0, 300)));
    if (rows.length < 2) continue;
    const complex = [...table.querySelectorAll('th,td')].some(c => c.colSpan > 1 || c.rowSpan > 1) || trs.some(tr => tr.cells.length > 12);
    tables.push({caption: table.caption?.innerText?.slice(0,200) || '', rows, complex, truncated:trs.length>41});
  }
  const document_links = [];
  for (const anchor of root?.querySelectorAll('a[href]') || []) {
    if (!visible(anchor) || document_links.length >= 8) continue;
    try {
      const url = new URL(anchor.href);
      if (/^https?:$/.test(url.protocol) && /\.pdf(?:$|[?#])/i.test(url.href)) document_links.push({title:anchor.innerText.slice(0,180),url:url.href});
    } catch { /* Not a document URL. */ }
  }
  const reviews = [];
  for (const el of root?.querySelectorAll('[itemprop="reviewBody"], [data-review-body], .review-text, .review-content, .comment-body') || []) {
    if (visible(el) && el.innerText.trim().length > 15) reviews.push(el.innerText.trim().slice(0,700));
    if (reviews.length >= 5) break;
  }
  const date = selector => document.querySelector(selector)?.getAttribute('content') || null;
  return {url:location.href,title:document.title,text,truncated:(root?.innerText || '').length>maxChars,
    publication_date:date('meta[property="article:published_time"],meta[name="date"],meta[name="pubdate"]') || [...(root?.querySelectorAll('time[datetime]') || [])].find(visible)?.getAttribute('datetime') || null,
    modified_date:date('meta[property="article:modified_time"],meta[name="last-modified"]'),
    excerpts,tables,document_links,reviews};
}

function enterGoogleQuery(query) {
  if (location.hostname !== 'www.google.com') throw new Error('Not Google');
  const input = document.querySelector('textarea[name="q"], input[name="q"]');
  if (!input || !input.form) return false;
  input.value = query;
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.form.requestSubmit();
  return true;
}

function scrollPublicDocument() {
  window.scrollBy(0, Math.min(700, window.innerHeight));
}

// Only visible DOM content; no hidden Google response scripts or network APIs.
function inspectMediaPage(kind, count) {
  const result = {url: location.href, title: document.title, text: (document.body?.innerText || '').slice(0, 1800), results: []};
  const seen = new Set();
  const external = value => {
    try {
      const u = new URL(value, location.href);
      if (/(^|\.)google\.[a-z.]+$/.test(u.hostname) && u.pathname === '/url') return external(u.searchParams.get('q') || u.searchParams.get('url'));
      return /^https?:$/.test(u.protocol) && !/(^|\.)google\.[a-z.]+$/.test(u.hostname) ? u.href : null;
    } catch { return null; }
  };
  const thumb = img => {
    const value = img?.currentSrc || img?.src || img?.getAttribute('data-src');
    if (!value || value.length > 40000) return null;
    return /^(?:https:\/\/|data:image\/(?:jpeg|png|webp);base64,)/.test(value) ? value : null;
  };
  const add = (title, url, thumbnail_url) => {
    if (!title?.trim() || !url || seen.has(url) || (kind === 'images' && !thumbnail_url)) return;
    seen.add(url); result.results.push({title: title.trim().slice(0, 180), url, thumbnail_url});
  };
  if (kind === 'videos') {
    for (const heading of document.querySelectorAll('a h3')) {
      if (!heading.getClientRects().length) continue;
      const anchor = heading.closest('a');
      let card = anchor;
      for (let i = 0; i < 4 && card && !card.querySelector('img'); i++) card = card.parentElement;
      add(heading.innerText, external(anchor.href), thumb(card?.querySelector('img')));
      if (result.results.length >= count) break;
    }
  } else {
    for (const img of document.querySelectorAll('img')) {
      if (!img.getClientRects().length || Math.max(img.width, img.naturalWidth) < 80) continue;
      if (img.closest('#tads, [data-text-ad], [aria-label="廣告"], [aria-label="贊助商廣告"]')) continue;
      let card = img, source = null, title = img.alt;
      for (let level = 0; level < 10 && card; level++, card = card.parentElement) {
        // A current Google image card has several nested wrappers. Stop
        // before crossing into a neighbour's result; small source favicons
        // do not count as a second result image.
        if ([...card.querySelectorAll('img')].filter(i => Math.max(i.width, i.naturalWidth) >= 80).length > 1) break;
        for (const a of card.querySelectorAll('a[href]')) {
          try {
            const u = new URL(a.href, location.href);
            source = external(u.searchParams.get('imgrefurl') || u.searchParams.get('refurl')) || external(a.href);
            if (source) { title = img.alt || a.innerText || a.getAttribute('aria-label'); break; }
          } catch { /* Ignore a malformed result link. */ }
        }
        if (source) break;
      }
      add(title, source, thumb(img));
      if (result.results.length >= count) break;
    }
  }
  return result;
}
