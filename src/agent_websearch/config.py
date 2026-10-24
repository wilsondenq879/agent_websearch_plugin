"""Generate local credentials; never distribute a paired browser extension."""
from importlib import resources
import json
import os
from pathlib import Path
import secrets


def home():
    return Path(os.environ.get("AGENT_WEBSEARCH_HOME", Path.home()/".agent-websearch")).expanduser()


def load(path=None):
    path=Path(path) if path else home()/"config.json"
    if path.is_symlink():
        raise ValueError("Refusing a symlinked credential file")
    try:
        config=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        raise ValueError("Run agent-websearch init first, or set AGENT_WEBSEARCH_HOME") from None
    if not isinstance(config,dict):raise ValueError("Invalid local configuration")
    port=config.get("port")
    if type(port) is not int or not 1024<=port<=65535:
        raise ValueError("Invalid local bridge port")
    keys=[config.get(k) for k in ("server_token","worker_token")]
    if any(not isinstance(k,str) or len(k)<32 or any(c.isspace() for c in k) for k in keys) or keys[0]==keys[1]:
        raise ValueError("Invalid or non-separated credentials; regenerate a local setup")
    return config


def init(state_dir=None,port=8769):
    root=Path(state_dir) if state_dir else home()
    if root.is_symlink():raise ValueError("Refusing a symlinked state directory")
    if type(port) is not int or not 1024<=port<=65535:raise ValueError("Use a port from 1024 to 65535")
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    root.chmod(0o700)
    path=root/"config.json"
    if path.exists():
        config=load(path)
        if config["port"]!=port:
            raise ValueError("Existing setup uses another port; use a new state directory to keep credentials intact")
    else:
        config={"protocol_version":1,"port":port,"server_token":secrets.token_urlsafe(40),"worker_token":secrets.token_urlsafe(40)}
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as handle:json.dump(config,handle,indent=2)
    extension=root/"extension"
    if extension.is_symlink():raise ValueError("Refusing a symlinked extension directory")
    extension.mkdir(exist_ok=True,mode=0o700)
    extension.chmod(0o700)
    for source in resources.files("agent_websearch").joinpath("extension").iterdir():
        if source.is_file():
            target=extension/source.name
            if target.is_symlink():raise ValueError("Refusing a symlinked extension asset")
            target.write_bytes(source.read_bytes())
    manifest=extension/"manifest.json"
    value=json.loads(manifest.read_text(encoding="utf-8"))
    value["content_security_policy"]["extension_pages"]=(
        "script-src 'self'; object-src 'none'; connect-src http://127.0.0.1:"+str(port))
    manifest.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    private=extension/"runtime-config.js"
    if private.is_symlink():raise ValueError("Refusing a symlinked runtime config")
    private.write_text("const EDGE_BRIDGE = Object.freeze("+json.dumps({
        "url":"http://127.0.0.1:"+str(port),"token":config["worker_token"]})+");\n",encoding="utf-8")
    private.chmod(0o600)
    return {"state_dir":str(root.resolve()),"extension_dir":str(extension.resolve()),
            "config_path":str(path.resolve()),"port":port,"credentials_printed":False}
