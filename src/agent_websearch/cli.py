import argparse
import json
from pathlib import Path
import sys

from .client import Client
from .config import home,init,load


def main():
    parser=argparse.ArgumentParser(description="Authenticated, bounded browser search for local agents")
    parser.add_argument("--state-dir",help="Private local setup directory (or AGENT_WEBSEARCH_HOME)")
    sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("init");create.add_argument("--port",type=int,default=8769)
    sub.add_parser("serve");sub.add_parser("status")
    for name in ("search","images","videos"):
        p=sub.add_parser(name);p.add_argument("query");p.add_argument("--count",type=int,default=6 if name=="search" else 2)
    for name in ("read","inspect"):
        p=sub.add_parser(name);p.add_argument("url");p.add_argument("--max-chars",type=int,default=7000)
        if name=="inspect":p.add_argument("--focus",default="")
    args=parser.parse_args()
    root=Path(args.state_dir) if args.state_dir else home()
    try:
        if args.command=="init":result=init(root,args.port)
        elif args.command=="serve":
            from .broker import make_server
            config=load(root/"config.json")
            with make_server(config) as server:
                print("Agent Websearch listening on 127.0.0.1:"+str(config["port"]),file=sys.stderr)
                server.serve_forever()
            return
        else:
            client=Client(root/"config.json")
            if args.command=="status":result=client.status()
            elif args.command=="search":result=client.search(args.query,args.count)
            elif args.command=="read":result=client.read(args.url,args.max_chars)
            elif args.command=="inspect":result=client.inspect(args.url,args.max_chars,args.focus)
            else:result=client.media(args.query,"images" if args.command=="images" else "videos",args.count)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if result.get("status") in ("error","human_required","empty"):raise SystemExit(1)
    except (ValueError,OSError) as error:
        print(json.dumps({"status":"error","message":str(error)},ensure_ascii=False))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__=="__main__":main()
