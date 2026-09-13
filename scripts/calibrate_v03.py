"""Predeclared mechanical acceptance on saved, held-out completed market bars."""
import json,time,urllib.request,hashlib,sys,argparse
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyterm.neural import FullBrain,market_frame,frame_png,output_fingerprint
from flyterm.records import canonical,atomic,digest
from flyterm.sensory import PARAMETERS
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,default=ROOT/"runs/calibration-new");args=parser.parse_args()
OUT=args.out
if OUT.exists() and any(OUT.iterdir()):raise SystemExit("Use a new empty calibration directory")
OUT.mkdir(parents=True,exist_ok=True)
spec={"encoder":PARAMETERS,"holdoutBars":64,"lookbackBars":120,"thresholds":{"minimumBuys":2,"minimumSells":2},"createdAt":int(time.time()*1000),
      "scope":"mechanical sensitivity and deterministic execution; no profitability gate","fittedOnHoldout":False}
atomic(OUT/"protocol.json",canonical(spec))
now=int(time.time()*1000)
req=urllib.request.Request("https://api.hyperliquid.xyz/info",data=json.dumps({"type":"candleSnapshot","req":{"coin":"BTC","interval":"1m","startTime":now-6*3600*1000,"endTime":now}}).encode(),headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=20) as r:raw=json.load(r)
bars=[{"time":int(c["t"]),"closeTime":int(c["T"]),"open":float(c["o"]),"high":float(c["h"]),"low":float(c["l"]),"close":float(c["c"]),"volume":float(c["v"])} for c in raw if int(c["T"])<now]
bars=sorted(bars,key=lambda c:c["time"])
if len(bars)<184:raise SystemExit("Insufficient historical bars")
atomic(OUT/"market.json",canonical(bars))
reports={}
for learning in [False,True]:
    label="learning" if learning else "frozen"
    brain=FullBrain(learning=learning)
    brain.checkpoint(OUT/(label+"-genesis.npz"))
    rows=[];counts={"BUY":0,"SELL":0,"HOLD":0}
    for i in range(len(bars)-64,len(bars)):
        c=bars[i]
        market={"providerTime":(c["closeTime"]+1)/1000,"candles":bars[max(0,i-119):i+1],"bid":c["close"],"ask":c["close"],"markPrice":c["close"]}
        frame=market_frame(market,"movement")
        out=brain.observe(frame,"none")
        counts[out["side"]]+=1
        rows.append({"barTime":c["time"],"market":market,"neural":out,"fingerprint":output_fingerprint(out),"inputPixelHash":hashlib.sha256(frame.tobytes()).hexdigest()})
    atomic(OUT/(label+"-rows.json"),canonical(rows))
    report={"counts":counts,"model":brain.identity(),"accepted":counts["BUY"]>=2 and counts["SELL"]>=2}
    reports[label]=report
    print(json.dumps({"arm":label,**counts,"accepted":report["accepted"]}),flush=True)
final={"schema":"flyterm-calibration/v03","protocol":spec,"reports":reports,"accepted":all(x["accepted"] for x in reports.values()),
       "modelSourceHash":digest(reports["learning"]["model"]["source"]),"kernel":reports["learning"]["model"]["build"],
       "proofType":"held-out mechanical check, not a profitability claim","at":int(time.time()*1000)}
atomic(OUT/"acceptance.json",canonical(final))
print(json.dumps({"accepted":final["accepted"],"modelSourceHash":final["modelSourceHash"]}),flush=True)
