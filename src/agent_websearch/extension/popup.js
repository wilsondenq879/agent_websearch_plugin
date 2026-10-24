let checking = false;
async function update() {
  if (checking) return;
  checking = true;
  const button = document.getElementById('refresh');
  const status = document.getElementById('status');
  const detail = document.getElementById('detail');
  button.disabled = true;
  status.setAttribute('aria-busy', 'true');
  status.textContent = '檢查連線中…';
  try {
    const value = await chrome.storage.local.get(['paused']);
    document.getElementById('paused').checked = !!value.paused;
    if (!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(EDGE_BRIDGE.url)) throw new Error('Invalid local setup');
    const response = await fetch(EDGE_BRIDGE.url + '/bridge/health', {
      headers: {'Authorization': 'Bearer ' + EDGE_BRIDGE.token},
      signal: AbortSignal.timeout(3000), cache: 'no-store', credentials: 'omit', redirect: 'error'
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const health = await response.json();
    const paused = !!value.paused || !!health.paused;
    const ready = !!health.connected && !paused;
    status.textContent = paused ? '已暫停' : ready ? '已連線' : '瀏覽器工作程序尚未連線';
    document.getElementById('dot').classList.toggle('connected', ready);
    detail.textContent = paused ? '恢復後才接受新的工作。' : ready ? (health.pending ? '正在處理 agent 工作。' : '等待已授權 agent 的工具呼叫。') : '本機服務已啟動；請重新載入這份擴充功能，並確認使用相同的配對資料夾。';
  } catch {
    status.textContent = '本機橋接服務未連線';
    document.getElementById('dot').classList.toggle('connected', false);
    detail.textContent = '請執行 agent-websearch serve，並確認它與這份擴充功能使用相同的設定。';
  } finally {
    button.disabled = false;
    status.removeAttribute('aria-busy');
    checking = false;
  }
}
document.getElementById('paused').addEventListener('change', async event => {
  await chrome.storage.local.set({paused: event.target.checked});
  await chrome.runtime.sendMessage({type: 'refresh'});
  update();
});
document.getElementById('refresh').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({type: 'refresh'});
  update();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.paused) update();
});
setInterval(update, 5000);
update();
