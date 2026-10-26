# Agent Websearch Plugin

讓不同 local agent 透過你電腦上的 Edge 查詢 Google、閱讀公開網頁，並取得有來源網址的資料。核心不依賴 Open WebUI、Ollama 或特定模型，也不需要搜尋 API key。

## 可以給哪些 agent 用？

| Agent 能力 | 接入方式 |
|---|---|
| 能呼叫 Python 或 HTTP | `Client` 或本機 HTTP API |
| 能執行本機指令 | CLI，回傳 JSON |
| 支援 MCP stdio | 可選的 MCP adapter |
| Open WebUI Workspace Tools | `adapters/openwebui.py` |

模型本身不會因為安裝這個套件就自動使用工具。Agent 需要註冊工具，並設定何時搜尋、何時閱讀來源，以及失敗時怎麼處理。多個 agent 可以共用服務，但同一時間只處理一個瀏覽器工作；其他請求會收到忙碌回應，需要由 agent 協調。

## 安裝

需要 Python 3.11+ 與 Edge。核心只使用 Python 標準函式庫，Node.js 只用於開發測試；MCP 是可選依賴。

```sh
git clone https://github.com/wilsondenq879/agent_websearch_plugin.git
cd agent_websearch_plugin
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
agent-websearch init
agent-websearch serve
```

Windows 請用 `python -m venv .venv`，並在 PowerShell 用 `.venv\Scripts\Activate.ps1` 啟用環境。

`init` 會印出產生的 extension 資料夾。到 Edge 手動開啟 `edge://extensions` →「開發人員模式」→「載入解壓縮」，選擇**產生的資料夾**，不要選 repo 內的原始碼資料夾。保持 `serve` 和 Edge 開啟，在另一個已啟用環境的終端機執行：

```sh
agent-websearch status
agent-websearch search "Python 官方文件" --count 6
agent-websearch read https://docs.python.org/3/
agent-websearch inspect https://docs.python.org/3/ --focus "tutorial"
agent-websearch images "光的折射 示意圖" --count 2
agent-websearch videos "光的折射 原理" --count 2
```

若已有舊版 Open WebUI 橋接使用 8769，不需要停止或覆蓋它。使用獨立資料夾與另一個 port：

```sh
agent-websearch --state-dir .state init --port 8770
agent-websearch --state-dir .state serve
```

再載入新的 `.state/extension`。使用其他 agent 時，也必須指定同一份本機設定，詳見英文 [README](README.md)。

## MCP

```sh
python -m pip install -e '.[mcp]'
```

將 [examples/mcp.json](examples/mcp.json) 的設定加入支援 MCP 的 client；設定位置依各 client 而異。若找不到指令，改填該虛擬環境內 `agent-websearch-mcp` 的完整路徑。MCP 程序不會代啟動瀏覽器或 broker，仍需先執行 `serve`。

提供 `browser_status`、`web_search`、`read_webpage`、`inspect_webpage`、`image_search`、`video_search` 六個工具。

### DeepSeek Harness Desktop（不用搜尋 API key）

DeepSeek Harness Desktop 可透過標準 MCP 直接使用這個本機 bridge；不需要啟用
DeepSeek 原生網路搜尋、不需要 DeepSeek 搜尋帳號，也不需要 Tavily、Google 或其他搜尋
API key。將 [examples/deepseek-harness.yaml](examples/deepseek-harness.yaml)
的 entry 加到應允許搜尋的 Harness profile／composition，並把兩個絕對路徑改成你的實際
位置。

`command` 必須指向此套件虛擬環境中的 `agent-websearch-mcp`；
`AGENT_WEBSEARCH_HOME` 必須和 `agent-websearch serve`、以及 Edge 載入的產生 extension
共用同一份本機 state directory。先安裝 MCP extra，並獨立啟動 broker：

```sh
python -m pip install -e '.[mcp]'
agent-websearch serve
```

Harness reload profile 後，模型會看見 `mcp__local_web__browser_status`、
`mcp__local_web__web_search`、`mcp__local_web__read_webpage`、
`mcp__local_web__inspect_webpage`、`mcp__local_web__image_search`、
`mcp__local_web__video_search`。新開桌面 session 時先用 `browser_status` 檢查連線；
若回傳 `human_required`，代表 Google 或網站需要你接手，不能偷偷改用未揭露的 API 搜尋。

## 資料品質與限制

- 搜尋預設最多 6 筆，不會為了湊數捏造結果。摘要不代表已閱讀來源，成功讀取頁面才有 `page_read: true`。
- 可取得可見表格、摘錄、頁面日期、評論樣本與 PDF 連結；不解析 PDF 二進位檔，不下載影片。查閱時間使用 UTC，不等於發表時間。
- 網頁內容是未受信任的來源資料；agent 不應遵從網頁中的工具指令，或把少數評論當成整體統計。
- Google 真人驗證、登入與安全攔截需要使用者處理，工具不會繞過。暫停、逾時或沒有結果都不能宣稱查證成功。
- 開源版不會自動使用 Tavily 等備援服務；是否備援由呼叫端設定。

## 權限與授權

服務只監聽 `127.0.0.1`，採 agent／extension 分離的金鑰。擴充功能使用 HTTP(S) 廣泛網站權限，但程式限制只操作自己建立的分頁；這不是瀏覽器權限層的隔離，也不是完整桌面操作工具。沒有截圖、列舉其他分頁、cookies／歷史 API、任意 JS、shell、發文或購買功能。

使用現有 Edge profile，網站仍可能依登入狀態個人化。只提供公開網址與公開搜尋詞，不要輸入機密。不要將服務對外公開。

每位使用者的配對金鑰在本機生成。**不要分享 `config.json`、`runtime-config.js` 或生成的 extension 資料夾**。Windows 使用者需自行確認資料夾的使用者權限。更多細節見 [SECURITY.md](SECURITY.md)。

程式採 [MIT](LICENSE) 授權；Google 結果、第三方圖片與影片不因此取得 MIT 授權。來源說明見 [NOTICE.md](NOTICE.md)。

驗證範圍：本機協定、DOM fixture、MCP 真實 stdio 握手與工具呼叫已測試；開源 Python client 也已透過既有 macOS Edge 橋接完成搜尋與閱讀。未宣稱已在所有作業系統安裝新版 extension 並實際操作瀏覽器。
