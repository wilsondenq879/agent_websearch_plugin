# Agent Websearch Plugin

[繁體中文說明](README.zh-TW.md)

**Give a local agent browser-backed Google search — without tying it to a
specific model or chat application.**

An authenticated loopback broker connects trusted local agents to an Edge
Manifest V3 extension. The extension opens its own temporary tabs, searches
Google, reads public pages, and returns structured, source-linked evidence.

繁體中文快速說明：這不是裝進模型的插件，而是提供給 agent 呼叫的搜尋工具。
能呼叫 HTTP、執行 CLI，或支援 MCP stdio 的 agent，都可以接入。模型是否
會正確使用工具，仍取決於它的工具能力與 agent 的路由設定。

## Interfaces

| Interface | For |
|---|---|
| Python / HTTP | Custom agents and orchestrators |
| CLI with JSON output | Agents that can run local commands |
| Optional MCP stdio server | MCP-capable clients |
| Optional Open WebUI tool | Workspace Tools integration |

No Open WebUI, Ollama, model, browser profile, or Tavily key is required by the
core package. Python 3.11+ and a running, user-controlled Edge installation
are required. Edge is the original tested browser; other Chromium MV3 browsers
may work but are not claimed as live-tested here. Firefox is not supported.

## Quick start

```sh
git clone https://github.com/wilsondenq879/agent_websearch_plugin.git
cd agent_websearch_plugin
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
agent-websearch init
agent-websearch serve
```

On Windows, use `python -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell instead of `source`.

`init` prints the **generated extension directory**, normally
`~/.agent-websearch/extension`, but never prints tokens.

1. In Edge, manually open `edge://extensions`.
2. Enable **Developer mode → Load unpacked**.
3. Select that **generated extension directory**, NOT the source folder in
   this repository. The generated folder contains your private pairing token.
4. Keep `agent-websearch serve` running. The extension polls it automatically.
5. In another activated terminal:

```sh
agent-websearch status
agent-websearch search "Python official documentation" --count 6
agent-websearch read https://docs.python.org/3/ --max-chars 7000
agent-websearch inspect https://docs.python.org/3/ --focus "tutorial"
agent-websearch images "rainbow refraction diagram" --count 2
agent-websearch videos "how rainbows form" --count 2
```

Search snippets are not full-page reads. Only a successful `read`/`inspect`
returns `page_read: true`. Source text remains untrusted reference data.

### Already running another bridge on port 8769?

Do not stop or overwrite it. Create an independent setup on another port:

```sh
agent-websearch --state-dir .state init --port 8770
agent-websearch --state-dir .state serve
agent-websearch --state-dir .state status
```

Load the new `.state/extension` folder for that independent setup. Alternatively
set `AGENT_WEBSEARCH_HOME` to a private directory. The CLI state option goes
**before** its subcommand. Keep generated state out of Git and public ZIPs.
Initialization is idempotent on the same port and does not rotate credentials.

## Python agent

```python
from agent_websearch import Client

client = Client()  # AGENT_WEBSEARCH_HOME or ~/.agent-websearch/config.json
search = client.search("Python official documentation", count=6)
if search.get("status") == "ok":
    source = client.read(search["results"][0]["url"], max_chars=7000)
    if source.get("page_read"):
        # Pass this as untrusted evidence to your model, retaining the URL.
        print(source["url"], source["text"])
```

See [examples/python_agent.py](examples/python_agent.py). Agents must stop or
ask the user when `status` is `human_required`; never claim success from an
`error` or `empty` result. The CLI returns nonzero for these outcomes.

## MCP adapter

```sh
python -m pip install -e '.[mcp]'
agent-websearch-mcp
```

The MCP process does **not** start the broker or browser. Run `serve` separately
and load your generated extension first. MCP stdio must not be exposed as a
remote network service.

Use [examples/mcp.json](examples/mcp.json) as a generic MCP client example;
configuration format/location is client-specific. If the client cannot find
your activated environment, replace `command` with the absolute path to its
`agent-websearch-mcp` executable. Set `AGENT_WEBSEARCH_HOME` in that client's
environment if using a nondefault setup. No token belongs in an MCP JSON file.

Tools: `browser_status`, `web_search`, `read_webpage`, `inspect_webpage`,
`image_search`, `video_search`. Tools return evidence, not an LLM-written answer.
No particular agent/model is advertised as automatically compatible without
tool configuration. The stdio protocol is tested with the Python MCP SDK.

### DeepSeek Harness Desktop

DeepSeek Harness Desktop can use this bridge through its standard MCP client;
it does **not** need DeepSeek native web search, a DeepSeek search account, or
any search API key. Copy the entry in
[examples/deepseek-harness.yaml](examples/deepseek-harness.yaml) into the
Harness profile/composition that should have search access, then replace both
absolute paths. The MCP command must point to this package's virtual
environment executable, and `AGENT_WEBSEARCH_HOME` must name the same local
state directory used by `agent-websearch serve` and the generated Edge
extension.

```sh
python -m pip install -e '.[mcp]'
agent-websearch serve
```

After Harness reloads its profile, the model sees
`mcp__local_web__browser_status`, `mcp__local_web__web_search`,
`mcp__local_web__read_webpage`, `mcp__local_web__inspect_webpage`,
`mcp__local_web__image_search`, and `mcp__local_web__video_search`. Check
`browser_status` first after starting a new desktop session. A `human_required`
result means Google or a site needs the user's intervention; do not retry it by
switching to a hidden API provider.

## Open WebUI adapter

Install this package in the **same Python environment** as Open WebUI. Import
[adapters/openwebui.py](adapters/openwebui.py) as a Workspace Tool and enable it
in the intended chat/model. The Open WebUI server must run under the user who
can access the local credential file, on the same machine as the broker.

This optional adapter is not automatically installed and does not modify an
existing Open WebUI runtime, model settings or search routing. Your application
may implement a disclosed fallback above this bridge; the generic extension
itself does not enable, bundle, or silently call a fallback service.

## HTTP protocol

All requests require `Host: 127.0.0.1:PORT` and
`Authorization: Bearer <locally generated credential>`.

| Endpoint | Credential | Purpose |
|---|---|---|
| `GET /api/health` | Agent/server token | Connection, pause and job state |
| `POST /api/run` | Agent/server token | Submit and wait for one bounded job |
| `POST /api/cancel` | Agent/server token | Cancel an owned request by job ID |
| `/bridge/*` | Extension/worker token | Extension polling/results only |

`/api/run` takes `{"id":"<32 lowercase hex characters>","payload":{...}}`.
Payload operations are `search`, `read`, `inspect` and `media_search`.
Use `Client` to generate IDs and avoid handling the credential yourself.
There is one global browser job at a time; other agents receive a busy error,
not a second parallel browser operation. Coordinate concurrent agents in your
orchestrator. The broker deadline is 48 seconds; the extension's page deadline
is at most 42 seconds. No retry loop or fabricated result padding is used.

## Permissions and limitations

Please read [SECURITY.md](SECURITY.md) before installing.

- Uses `scripting`, `storage`, `alarms` and broad HTTP(S) host permissions.
  Owned-tab restrictions are code checks, not browser-enforced URL isolation.
- No other-tab enumeration, cookies/history APIs, arbitrary shell/JS, account
  reading, purchases, uploads or screenshots. This is **not** unrestricted
  desktop Computer Use and is **not** a network security sandbox.
- Uses your current browser profile. Public results can be personalized.
  Known login/account/private-network targets are rejected, but supply public
  URLs only; arbitrary site-specific private paths cannot be recognized fully.
- Source dates, exact tables and review samples are returned when visible,
  not independently fact-checked. `checked_at` is a UTC read timestamp, not a
  publication date. PDF links may be discovered; this release does not parse
  PDF binaries or download videos.
- Google UI/selector changes, consent dialogs, CAPTCHA, suspended extension
  workers and sleeping browsers can require manual intervention. No Google
  availability guarantee, CAPTCHA bypass, proxy rotation or stealth is offered.
- Images/videos are references with source links. Their copyright does not
  change because the software is MIT-licensed.

## Troubleshooting

If `connected` is false, confirm `serve` is running with the matching state
directory, Edge is open, and the generated extension is enabled and not paused.
Reload the extension after changing its code. The popup's **重新檢查連線**
button checks the broker directly rather than trusting an old status display.
Never share the generated extension or post `config.json` in an issue.

## Development and tests

```sh
python -m pip install -e '.[mcp]'
python -m unittest discover -s tests -v
node tests/test-dom.mjs
```

Tests use temporary credentials, a local fake worker and static DOM fixtures;
CI does not search Google or access a user's browser. The optional MCP test
exercises an actual stdio MCP session and the broker. The original Edge search
implementation was exercised live on macOS; cross-platform CI tests Python
and protocol behavior, not interactive Windows/Linux browser installations.
The extracted Python client was also checked against the existing macOS Edge
bridge: three Google results and a successful read of the Python documentation.
This does not substitute for installing the newly generated extension on every
supported operating system.

## License

[MIT](LICENSE). See [NOTICE.md](NOTICE.md) for provenance and third-party scope.
