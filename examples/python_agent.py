"""Run only after init, serve and loading your own generated extension."""
from agent_websearch import Client

client=Client()
health=client.status()
if not health.get("connected") or health.get("paused"):
    raise SystemExit("Browser worker is offline or paused. Check the extension.")

results=client.search("Python official documentation",count=3)
if results.get("status")!="ok":
    raise SystemExit(results.get("message","Search did not finish"))
for item in results["results"]:
    print(item["title"],item["url"])

# A separate read is necessary before claiming the page was read.
page=client.read(results["results"][0]["url"],max_chars=3000)
if page.get("page_read"):
    print(page["text"])
else:
    print(page.get("message","No readable source"))
