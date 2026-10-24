/* No external messages, tab enumeration, profile reads, arbitrary clicks or eval. */
importScripts('runtime-config.js', 'page-functions.js');

let polling = false;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const privateHosts = new Set(['accounts.google.com', 'mail.google.com', 'drive.google.com',
  'docs.google.com', 'outlook.live.com', 'outlook.office.com', 'outlook.office365.com',
  'teams.microsoft.com', 'login.microsoftonline.com', 'login.live.com', 'account.microsoft.com']);

function publicURL(value) {
  const u = new URL(value);
  const h = u.hostname.toLowerCase();
  if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password ||
      (u.port && !['80', '443'].includes(u.port)) || privateHosts.has(h) ||
      h === 'localhost' || !h.includes('.') || /\.(local|localhost|internal)$/.test(h) ||
      /^(127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.)/.test(h) ||
      /\/(login|signin|sign-in|account|settings)(\/|$)/i.test(u.pathname)) {
    throw new Error('只可操作公開網頁，不讀取本機、帳戶或管理頁面。');
  }
  return u.href;
}

async function bridge(path, body) {
  const response = await fetch(EDGE_BRIDGE.url + path, {method: body ? 'POST' : 'GET',
    headers: {'Authorization': 'Bearer ' + EDGE_BRIDGE.token, 'Content-Type': 'application/json'},
    ...(body ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(23000),
    cache: 'no-store', credentials: 'omit', redirect: 'error'});
  if (!response.ok) throw new Error('本機橋接暫時無法連線（' + response.status + '）');
  return response.json();
}

async function ownedTab(tabId) {
  const owned = (await chrome.storage.session.get('owned')).owned || [];
  if (!owned.includes(tabId)) throw new Error('不是工具建立的分頁。');
  const tab = await chrome.tabs.get(tabId);
  publicURL(tab.url || tab.pendingUrl);
  return tab;
}

async function inject(tabId, func, args = []) {
  await ownedTab(tabId);
  const output = await chrome.scripting.executeScript({target: {tabId}, func, args});
  return output[0]?.result;
}

function blocked(page) {
  const u = new URL(page.url);
  if (u.pathname.startsWith('/sorry') || /captcha|just a moment|privacy error|security check|access denied|驗證您是真人/i.test(page.title) ||
      /our systems have detected unusual traffic|verify you are human|checking your browser|連線不是私人連線/.test(page.text)) {
    return '網站要求真人驗證或顯示安全攔截；工具已停止，請由你接手。';
  }
  return null;
}

async function runJob(job) {
  if (!job || !/^[a-f0-9]{32}$/.test(job.id) || !['search', 'read', 'inspect', 'media_search'].includes(job.payload?.operation)) {
    throw new Error('不支援此工作。');
  }
  const p = job.payload;
  if (p.operation === 'search' && (typeof p.query !== 'string' || p.query.length > 500 || !Number.isInteger(p.count) || p.count < 1 || p.count > 6)) {
    throw new Error('無效的搜尋條件。');
  }
  if (['read','inspect'].includes(p.operation) && (!Number.isInteger(p.max_chars) || p.max_chars < 1000 || p.max_chars > 20000)) {
    throw new Error('無效的正文上限。');
  }
  if (p.operation === 'inspect' && (typeof p.focus !== 'string' || p.focus.length > 160 || typeof p.screenshot !== 'boolean')) throw new Error('無效的證據擷取條件。');
  if (p.operation === 'inspect' && p.screenshot) throw new Error('Screenshots are not enabled in this release.');
  if (p.operation === 'media_search' && (!['images', 'videos'].includes(p.media_type) || typeof p.query !== 'string' || !p.query.trim() || p.query.length > 500 || !Number.isInteger(p.count) || p.count < 1 || p.count > 3)) {
    throw new Error('無效的媒體搜尋條件。');
  }
  const mediaURL = p.operation === 'media_search' ? 'https://www.google.com/search?hl=zh-TW&' + new URLSearchParams({q: p.query, udm: p.media_type === 'images' ? '2' : 'vids'}) : null;
  const url = mediaURL || (p.operation === 'search' ? 'https://www.google.com/' : publicURL(p.url));
  const window = await chrome.windows.create({url, focused: false, type: 'normal', width: 1100, height: 820});
  const tabId = window.tabs[0].id;
  const owned = (await chrome.storage.session.get('owned')).owned || [];
  await chrome.storage.session.set({owned: [...owned, tabId]});
  let leaveOpen = false;
  let submitted = p.operation !== 'search';
  let nextAliveCheck = 0;
  const deadline = Math.min(job.expires_at, Date.now() + 42000);
  // Independent cleanup also runs if an injection stalls. Only this owned tab.
  const cleanup = setTimeout(() => chrome.tabs.remove(tabId).catch(() => {}), Math.max(0, deadline - Date.now()));
  try {
    while (Date.now() < deadline) {
      if (Date.now() >= nextAliveCheck) {
        if ((await chrome.storage.local.get('paused')).paused) throw new Error('橋接已暫停，工作已停止。');
        if (!(await bridge('/bridge/active/' + job.id)).active) throw new Error('工作已取消或逾時。');
        nextAliveCheck = Date.now() + 2000;
      }
      const tab = await ownedTab(tabId);
      if (tab.status !== 'complete') { await delay(300); continue; }
      if (!submitted) {
        submitted = await inject(tabId, enterGoogleQuery, [p.query]);
        if (!submitted) throw new Error('Google 搜尋欄位無法使用；沒有自動繞過同意或驗證畫面。');
        await delay(350);
        continue;
      }
      if (p.operation === 'search' && !new URL(tab.url).pathname.startsWith('/search') && !new URL(tab.url).pathname.startsWith('/sorry')) {
        await delay(300); continue;
      }
      const page = p.operation === 'media_search' ? await inject(tabId, inspectMediaPage, [p.media_type, p.count]) : await inject(tabId, inspectPage, [['read','inspect'].includes(p.operation) ? p.max_chars : 12000, p.operation === 'search' ? p.count : 0]);
      const reason = blocked(page);
      if (reason) {
        leaveOpen = true;
        await chrome.windows.update(window.id, {focused: true});
        return {status: 'human_required', message: reason};
      }
      if (p.operation === 'search' && !page.results.length) { await delay(500); continue; }
      if (p.operation === 'media_search' && !page.results.length) {
        await inject(tabId, scrollPublicDocument);
        await delay(300);
        return {status: 'ok', ...(await inject(tabId, inspectMediaPage, [p.media_type, p.count]))};
      }
      if (['read','inspect'].includes(p.operation)) {
        await inject(tabId, scrollPublicDocument);
        await delay(200);
        const full = await inject(tabId, inspectEvidence, [p.max_chars, p.focus || '']);
        if (blocked(full)) return {status:'human_required',message:blocked(full)};
        return {status: 'ok', ...full};
      }
      return {status: 'ok', ...page};
    }
    throw new Error('網頁載入逾時；沒有回傳未驗證的結果。');
  } finally {
    clearTimeout(cleanup);
    if (!leaveOpen) await chrome.tabs.remove(tabId).catch(() => {});
    const current = (await chrome.storage.session.get('owned')).owned || [];
    await chrome.storage.session.set({owned: current.filter(id => id !== tabId)});
  }
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    // Bounded iterations; alarms recover after MV3 worker suspension.
    for (let i = 0; i < 100; i++) {
      const paused = !!(await chrome.storage.local.get('paused')).paused;
      const {job} = await bridge('/bridge/next?max_count=6&media=1&research=1' + (paused ? '&paused=1' : ''));
      await chrome.storage.local.set({connected: true, updatedAt: Date.now(), error: ''});
      if (paused) break;
      if (job) {
        let result;
        try {
          if ((await chrome.storage.local.get('paused')).paused) throw new Error('橋接已暫停，未開始工作。');
          result = await runJob(job);
        }
        catch (error) { result = {status: 'error', message: error.message}; }
        await bridge('/bridge/result', {id: job.id, result});
        await chrome.storage.local.set({lastResult: result.status, updatedAt: Date.now()});
      }
    }
  } catch (error) {
    await chrome.storage.local.set({connected: false, error: error.message, updatedAt: Date.now()});
  } finally { polling = false; }
}

chrome.alarms.onAlarm.addListener(() => poll());
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('bridge-heartbeat', {periodInMinutes: 0.5});
  poll();
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create('bridge-heartbeat', {periodInMinutes: 0.5});
  poll();
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.tab) return false;
  if (message?.type === 'refresh') { poll(); reply({ok: true}); }
  return false;
});
// If a worker was suspended mid-job, clean up only remembered owned tabs.
(async () => {
  const owned = (await chrome.storage.session.get('owned')).owned || [];
  for (const id of owned) await chrome.tabs.remove(id).catch(() => {});
  await chrome.storage.session.set({owned: []});
  poll();
})();
