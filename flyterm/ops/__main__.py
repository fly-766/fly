import argparse,json,os
from pathlib import Path
from .codec import object_hash
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    from flyterm.records import atomic,canonical
    atomic(Path(p),canonical(v));print(json.dumps({"file":str(p),"sha256":object_hash(v),"liveEnabled":v.get("liveEnabled",False)}))
def main():
    ap=argparse.ArgumentParser(description="FlyTerm v0.4 local preparation and explicitly armed execution")
    sub=ap.add_subparsers(dest="command",required=True)
    d=sub.add_parser("prepare-deploy");d.add_argument("--roles",required=True);d.add_argument("--token",required=True);d.add_argument("--manifest",required=True);d.add_argument("--out",required=True)
    l=sub.add_parser("prepare-launch");l.add_argument("--draft",required=True);l.add_argument("--creator",required=True);l.add_argument("--quote",required=True);l.add_argument("--out",required=True)
    v=sub.add_parser("validate-launch");v.add_argument("--response",required=True);v.add_argument("--expected",required=True);v.add_argument("--limits",required=True);v.add_argument("--manager",required=True);v.add_argument("--out",required=True)
    c=sub.add_parser("prepare-keeper");c.add_argument("--deployment",required=True);c.add_argument("--keeper",required=True);c.add_argument("--xlayer-from",type=int,required=True);c.add_argument("--hyper-from",type=int,required=True);c.add_argument("--funding-from-ms",type=int,required=True);c.add_argument("--run",required=True);c.add_argument("--out",required=True)
    pin=sub.add_parser("pin-runtime");pin.add_argument("--config",required=True);pin.add_argument("--out",required=True)
    init=sub.add_parser("init-run");init.add_argument("--out",required=True)
    replay=sub.add_parser("replay-contract-run");replay.add_argument("--run",required=True)
    for name in ("step","run"):
        k=sub.add_parser(name);k.add_argument("--config",required=True);k.add_argument("--state",required=True);k.add_argument("--live",action="store_true");k.add_argument("--approved-config-hash");k.add_argument("--observe",action="store_true")
    tx=sub.add_parser("dispatch");tx.add_argument("--profile",required=True);tx.add_argument("--intent",required=True);tx.add_argument("--state",required=True);tx.add_argument("--live",action="store_true");tx.add_argument("--approved-config-hash")
    status=sub.add_parser("status");status.add_argument("--state",required=True)
    a=ap.parse_args()
    if a.command=="prepare-deploy":
        from .deployment import prepare
        write(a.out,prepare(read(a.roles),a.token,read(a.manifest)))
    elif a.command=="prepare-launch":
        from .launch import request
        write(a.out,request(read(a.draft),a.creator,a.quote))
    elif a.command=="validate-launch":
        from .launch import validate_response
        write(a.out,validate_response(read(a.response),read(a.expected),read(a.limits),a.manager))
    elif a.command=="prepare-keeper":
        from .configuration import keeper_config
        from .deployment import ROOT
        write(a.out,keeper_config(read(a.deployment),read(ROOT/"config/protocol-addresses.json"),a.keeper,{"xlayer":a.xlayer_from,"hyper":a.hyper_from},a.funding_from_ms,a.run))
    elif a.command=="pin-runtime":
        from .rpc import Rpc
        from .codec import raw
        from eth_utils import keccak
        c=read(a.config)
        for chain in c["chains"].values():
            rpc=Rpc(os.environ.get(chain["rpcEnv"]),chain["chainId"]);rpc.verify_chain();pins={}
            for addr in chain["allowedCalls"]:
                code=raw(rpc.code(addr))
                if not code:raise ValueError("Expected deployed project contract absent")
                pins[addr]="0x"+keccak(code).hex()
            chain["runtimeCodeHashes"]=pins
        write(a.out,c)
    elif a.command=="init-run":
        from flyterm.live import LiveBrain
        b=LiveBrain(a.out)
        try:print(json.dumps({"runId":b.manifest["runId"],"manifest":str(Path(a.out)/"manifest.json"),"signingEnabled":False}))
        finally:b.close()
    elif a.command=="replay-contract-run":
        from flyterm.live import replay
        print(json.dumps(replay(a.run)))
    elif a.command in ("step","run"):
        from .keeper import Keeper
        c=read(a.config);brain=None
        if a.observe:
            from flyterm.live import LiveBrain
            brain=LiveBrain(c["runDirectory"])
        keeper=None
        try:
            keeper=Keeper(c,a.state,live=a.live,approved=a.approved_config_hash,brain=brain)
            if a.command=="step":print(json.dumps(keeper.step(),ensure_ascii=False))
            else:keeper.run()
        finally:
            if keeper:keeper.close()
            if brain:brain.close()
    elif a.command=="dispatch":
        from .executor import Executor
        from .rpc import Rpc
        from .journal import OperationJournal
        c=read(a.profile);rpc=Rpc(os.environ.get(c["rpcEnv"]),c["chainId"]);j=OperationJournal(Path(a.state)/"operations.sqlite")
        try:print(json.dumps(Executor(c,j,rpc).submit("reviewed_dispatch",read(a.intent),live=a.live,approved_hash=a.approved_config_hash)))
        finally:j.close()
    else:
        p=Path(a.state)/"health.json";print(p.read_text() if p.exists() else '{"state":"not_started"}')
if __name__=="__main__":main()
