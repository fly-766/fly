"""Loopback-only public viewer. No financial write endpoints."""
import argparse
import json
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from market import MarketCache
from flyterm.api import status,calibration
from flyterm.records import Journal

ROOT=Path(__file__).resolve().parent
CACHE=MarketCache()
RUN=ROOT/"runs/v03-live-observation"
OPS=None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/"web"),**kwargs)
    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        super().end_headers()
    def list_directory(self,path):self.send_error(404)
    def output_json(self,value,status_code=200):
        body=json.dumps(value,allow_nan=False).encode()
        self.send_response(status_code);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        parsed=urlsplit(self.path);path=parsed.path
        if path=="/api/market":
            value=CACHE.get();return self.output_json(value,200 if value["ok"] else 503)
        if path in ("/api/state","/api/run"):
            value=status(RUN)
            public=OPS/"public.json" if OPS else None
            if public and public.exists():
                from flyterm.records import digest
                ops=json.loads(public.read_text());anchor=ops.get("onchain",{})
                if value.get("ok") and anchor.get("runId")=="0x"+digest(value["runId"]):value["anchor"]=anchor
            return self.output_json(value)
        if path=="/api/operations":
            f=OPS/"public.json" if OPS else None
            return self.output_json(json.loads(f.read_text()) if f and f.exists() else {"ok":False,"deployment":"not_deployed","liveEnabled":False})
        if path in ("/api/launch","/api/verify","/api/verification"):
            from flyterm.launch_status import public_status
            return self.output_json(public_status())
        if path=="/api/health":
            import time
            f=OPS/"public.json" if OPS else None
            try:ops=json.loads(f.read_text()) if f and f.exists() else {}
            except (OSError,ValueError):ops={}
            age=max(0,int(time.time()*1000)-int(ops.get("at",0))) if ops.get("at") else None
            return self.output_json({"schema":"fly-health/v1","viewerReady":True,"operationsConfigured":bool(OPS),"operationsFresh":age is not None and age<=90000,"operationsAgeMs":age,"liveEnabled":bool(ops.get("liveEnabled")) and age is not None and age<=90000})
        if path=="/api/acceptance":
            f=ROOT/"release/acceptance-v03.json"
            return self.output_json(json.loads(f.read_text()) if f.exists() else {"ok":False})
        if path=="/api/calibration":return self.output_json(calibration(ROOT/"runs/calibration-v03"))
        if path in ("/api/manifest","/api/records"):
            if not (RUN/"journal.sqlite").exists():return self.output_json({"ok":False},404)
            j=Journal(RUN,readonly=True)
            try:
                if path=="/api/manifest":value=j.meta("manifest")
                else:
                    raw=parse_qs(parsed.query).get("limit",["20"])[0]
                    if not raw.isdigit():return self.output_json({"ok":False},400)
                    value=j.rows(min(int(raw),100))
                return self.output_json(value)
            finally:j.close()
        if path.startswith("/api/artifacts/"):
            j=None
            try:
                j=Journal(RUN,readonly=True);f=j.artifact_path(path.removeprefix("/api/artifacts/"))
                self.send_response(200)
                self.send_header("Content-Type","image/png" if f.suffix==".png" else "application/octet-stream")
                self.send_header("Content-Length",str(f.stat().st_size));self.send_header("Cache-Control","public,max-age=31536000,immutable");self.end_headers()
                with f.open("rb") as source:
                    while block:=source.read(1024*1024):self.wfile.write(block)
            except (ValueError,FileNotFoundError):self.send_error(404)
            finally:
                if j:j.close()
            return
        if path.startswith("/api/"):self.send_error(404);return
        super().do_GET()
    def do_POST(self):self.send_error(405,"Read-only viewer")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8797);parser.add_argument("--run",type=Path,default=RUN);parser.add_argument("--ops",type=Path)
    parser.add_argument("--instance",type=Path)
    args=parser.parse_args();RUN=args.run.resolve();OPS=args.ops.resolve() if args.ops else None
    if args.instance:
        import os
        os.environ["FLYTERM_INSTANCE_FILE"]=str(args.instance.resolve())
    print(f"FlyTerm: http://127.0.0.1:{args.port} (viewer only)",flush=True)
    ThreadingHTTPServer(("127.0.0.1",args.port),Handler).serve_forever()
