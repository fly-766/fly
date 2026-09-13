#!/usr/bin/env python3
"""Generate unsigned registry data. Never imports a wallet or sends an RPC write."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flyterm.records import Journal,digest

def prepare(directory):
    j=Journal(directory,readonly=True)
    try:
        audit=j.audit();m=j.meta("manifest");records=j.rows()
        out={"schema":"flyterm-unsigned-record/v1","executable":False,"signingEnabled":False,
             "broadcastEnabled":False,"attestation":"operator-signature-not-computation-proof",
             "registryConstructor":{"runId":"0x"+hashlib.sha256(m["runId"].encode()).hexdigest(),
                                    "modelHash":"0x"+digest(m["model"]),"genesis":"0x"+m["genesisState"],"attestor":None},
             "domain":{"name":"FlyTerm Decision","version":"1","chainId":None,"verifyingContract":None},
             "currentLocalHead":"0x"+audit["head"],"decisions":[]}
        for row in records:
            b=row["body"]
            out["decisions"].append({"sequence":row["seq"],"observedAt":b["wallTime"]//1000,
                                    "deadline":b["wallTime"]//1000+120,"previousState":"0x"+b["previousState"],
                                    "nextState":"0x"+b["nextState"],"inputHash":"0x"+b["neural"]["input_sha256"],
                                    "recordHash":"0x"+row["root"],"side":{"HOLD":0,"BUY":1,"SELL":2}[b["neural"]["side"]]})
        return out
    finally:j.close()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",type=Path,default=ROOT/"runs/v02-accepted")
    a=p.parse_args();print(json.dumps(prepare(a.run),indent=2))
