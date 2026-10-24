"""Small stdlib-only agent client. All actions go through one fixed local broker."""
import json
from pathlib import Path
import urllib.error
import urllib.request
import uuid

from .config import load


class Client:
    def __init__(self,config_path: str | Path | None=None):
        self._config=load(config_path)

    def _request(self,path,payload=None,timeout=53):
        if path not in ("/api/run","/api/cancel","/api/health"):
            raise ValueError("Unsupported local endpoint")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*_):return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        request=urllib.request.Request("http://127.0.0.1:"+str(self._config["port"])+path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization":"Bearer "+self._config["server_token"],"Content-Type":"application/json"})
        try:
            with opener.open(request,timeout=timeout) as response:raw=response.read(1800001)
        except urllib.error.HTTPError as error:
            if error.code!=400:
                return {"status":"error","code":"bridge_http_error","message":"Local bridge rejected the request (HTTP "+str(error.code)+")"}
            raw=error.read(4096)
        except (urllib.error.URLError,OSError):
            return {"status":"error","code":"bridge_unavailable","message":"Local bridge unavailable; check the server, browser extension and its pause switch"}
        if len(raw)>1800000:raise ValueError("Bridge response exceeds the safety limit")
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError("Invalid bridge response")
        return result

    def status(self):
        return self._request("/api/health",timeout=3)

    def run(self,payload):
        identifier=uuid.uuid4().hex
        try:return self._request("/api/run",{"id":identifier,"payload":payload})
        except BaseException:
            # A cancellation never starts another job or changes user tabs.
            self._request("/api/cancel",{"id":identifier},timeout=3)
            raise

    def search(self,query,count=6):
        return self.run({"operation":"search","query":query,"count":count})

    def read(self,url,max_chars=7000):
        return self.run({"operation":"read","url":url,"max_chars":max_chars})

    def inspect(self,url,max_chars=12000,focus=""):
        return self.run({"operation":"inspect","url":url,"max_chars":max_chars,"focus":focus,"screenshot":False})

    def media(self,query,media_type,count=2):
        return self.run({"operation":"media_search","query":query,"media_type":media_type,"count":count})
