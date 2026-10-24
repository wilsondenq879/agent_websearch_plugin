# Provenance and third-party services

This repository extracts the independently developed local browser bridge,
extension and evidence utilities from a custom Open WebUI integration. It does
not contain upstream Open WebUI/Desktop source, application binaries, model
weights, icon packs, browser profile files, or browser cookies.

The repository's existing MIT license is retained. Dependencies, browsers,
websites and retrieved media retain their respective licenses and terms. MIT
does not grant rights to Google results, third-party images or video content.

The extension contains no remote scripts or vendored JavaScript dependencies.
MCP support is optional and uses the separately installed Python MCP SDK.

The Open WebUI adapter is optional; no Open WebUI import is required by the
core package, broker, CLI, or browser extension. Existing application-specific
routing (such as Tavily fallback) belongs to the calling agent, not the generic
browser extension.
