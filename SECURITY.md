# Security model

- This is a same-user local tool bridge, not an unrestricted desktop agent or
  a security sandbox. Only give its agent credential to trusted local agents.
- The broker binds **127.0.0.1 only**. Do not reverse-proxy, port-forward or
  expose it on a LAN, VPN, container published port, or the public Internet.
- Every request requires a generated bearer token. Agent and extension tokens
  are different: the extension can consume jobs, but cannot create them.
  Unknown browser origins and incorrect Host headers are rejected.
- Searches and reads can open tabs ONLY in dedicated tool-created windows.
  There is no tab enumeration, cookies/history API, shell/eval, arbitrary
  clicking, login, upload, purchase or screenshot operation.
- `http://*/*` and `https://*/*` host permissions are nevertheless broad.
  Owned-tab restrictions are application code, not browser-enforced URL
  isolation. Future extension updates deserve review before installation.
- Browsing uses the active browser profile; sites may personalize public
  content. Known account/login/private-network paths are denied, but arbitrary
  application-specific private paths cannot be identified perfectly. Supply
  public URLs only. Never send internal documents, whole chats or credentials.
- DNS/private-IP checks apply to submitted and returned URLs. These are not a
  browser network firewall and cannot pin a browser navigation across DNS
  changes/redirects. Do not use the extension as an SSRF isolation boundary.
- CAPTCHA, login, security interstitials and detected access blocks stop work;
  no challenge solving, stealth, proxy rotation or fallback service is used.
- One browser job runs at a time. `human_required`, `empty`, timeout and busy
  responses are not successful searches. Never manufacture missing evidence.
- Source text is untrusted data. An agent must not follow instructions in
  scraped text, reveal credentials, or treat visible reviews as a population.

`agent-websearch init` creates credentials under a private local state folder;
do not publish that folder or its generated extension. POSIX permissions are
restricted where supported; on Windows protect the folder with user-only ACLs.
Generated `runtime-config.js` contains the worker token and is gitignored.

If credentials leak, stop the broker, create a new state directory, generate a
fresh setup, and reload the new generated extension. Never paste keys into an
issue. For a suspected vulnerability, contact the repository owner privately
before disclosing details; do not include private URLs or browser captures.
