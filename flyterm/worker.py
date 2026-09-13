"""Bounded or continuous SHADOW observation, with replayable full-brain state."""
import argparse
import fcntl
import json
import os
import time
import uuid
from pathlib import Path
from PIL import Image
from market import fetch_market
from .calibration import verify as verify_calibration,runtime_manifest
from .account import D, ShadowAccount, ShadowGuard
from .records import Journal, canonical, digest, atomic
from .neural import FullBrain, frame_png, market_frame, output_fingerprint, read_frame

ROOT=Path(__file__).resolve().parents[1]

def checkpoint(brain,journal,label):
    scratch=journal.root/(label+".npz")
    brain.checkpoint(scratch)
    artifact=journal.artifact(scratch.read_bytes(),".npz")
    scratch.unlink()
    return artifact

def restore_committed(brain,journal):
    manifest=journal.meta("manifest")
    rows=journal.rows()
    latest=manifest["genesis"]
    after=0
    for row in rows:
        if row["body"].get("checkpoint"):
            latest=row["body"]["checkpoint"];after=row["seq"]
    brain.restore(journal.artifact_path(latest["name"]))
    for row in rows:
        b=row["body"]
        if row["seq"]<=after or b.get("kind")!="observation":continue
        if brain.state_fingerprint()!=b["previousState"]:raise RuntimeError("Recovery previous state differs")
        out=brain.observe(read_frame(journal.artifact_path(b["input"]["name"])),b["reinforcement"])
        if brain.state_fingerprint()!=b["nextState"]:raise RuntimeError("Recovery next state differs")
        if output_fingerprint(out)!=b["neuralFingerprint"]:raise RuntimeError("Recovery replay diverged")
    return rows

def run(directory,steps=0,interval=60,adapter="movement",market_replay=None):
    if interval<5:raise ValueError("Minimum observation interval is 5 seconds")
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    lock=(directory/"worker.lock").open("ab")
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another worker owns this run")
    journal=Journal(directory)
    policy=json.loads((ROOT/"policy.json").read_text())
    if policy["liveEnabled"] or policy["execution"]!="shadow":raise RuntimeError("This runner has no real-money execution")
    brain=FullBrain(learning=policy["modelLearning"])
    identity=brain.identity()
    calibration=verify_calibration(ROOT/policy["calibrationReport"],identity,policy["calibrationReportSha256"])
    runtime=runtime_manifest(ROOT)
    replay_markets=json.loads(Path(market_replay).read_text()) if market_replay else None
    replay_hash=digest(replay_markets) if replay_markets else None
    manifest=journal.meta("manifest")
    if manifest:
        if manifest["policy"]!=policy or manifest["model"]!=identity or manifest["adapter"]!=adapter or manifest.get("runtimeSource")!=runtime or manifest.get("marketReplayHash")!=replay_hash:
            raise RuntimeError("Run identity changed; start a separate run")
        journal.audit()
        rows=restore_committed(brain,journal)
    else:
        genesis=checkpoint(brain,journal,"genesis")
        manifest={"schema":"flyterm-run/v1","stateHashSchema":"typed-clock-v2","runId":str(uuid.uuid4()),"createdAt":int(time.time()*1000),
                  "model":identity,"policy":policy,"adapter":adapter,"genesis":genesis,"genesisState":brain.state_fingerprint(),
                  "runtimeSource":runtime,"marketReplayHash":replay_hash,"calibration":calibration,"marketMode":"archived-public" if replay_markets else "live-public",
                  "mode":"shadow","executionEnabled":False,"attestation":"public-replay-not-zk",
                  "shadowCapitalUsdc":"500","capitalSource":"500 USDC simulated balance; no user funds"}
        journal.initialize(manifest)
        atomic(directory/"manifest.json",canonical(manifest))
        import shutil
        for rel in set(manifest["model"]["source"])|set(runtime):
            src=ROOT/rel
            if not src.resolve().is_relative_to(ROOT):raise ValueError("Invalid source manifest path")
            dst=directory/"source"/rel
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        rows=[]
    observations=[r["body"] for r in rows if r["body"].get("kind")=="observation"]
    account=ShadowAccount(state=observations[-1]["account"] if observations else None)
    guard=ShadowGuard(policy,[r["neural"]["side"] for r in observations[-policy["biasWindow"]:]])
    anchor=D(observations[-1]["reinforcementAnchor"]) if observations else account.principal
    count=0
    print(json.dumps({"runId":manifest["runId"],"resumedAfter":len(rows),"brain":identity["dataset"],"mode":"shadow"}),flush=True)
    try:
        while not steps or count<steps:
            start=time.monotonic()
            if (directory/"STOP").exists():break
            seq=len(rows)+1
            try:
                if replay_markets:
                    if len(rows)>=len(replay_markets):break
                    market=replay_markets[len(rows)]
                else:
                    market=fetch_market()
                    if observations:
                        prev=observations[-1]["market"]
                        old=max(c["closeTime"] for c in prev["candles"] if c["closeTime"]<=prev["providerTime"]*1000)
                        new=max(c["closeTime"] for c in market["candles"] if c["closeTime"]<=market["providerTime"]*1000)
                        if new<=old:
                            time.sleep(min(5,interval));continue
                completed=[c for c in market["candles"] if c["closeTime"]<=market["providerTime"]*1000]
                if any(b["time"]-a["time"]!=60000 for a,b in zip(completed[-62:],completed[-61:])):raise ValueError("Completed market bars contain gaps")
                account.mark(market)
                equity=account.equity(market["markPrice"])
                delta=equity-anchor
                reinforcement="reward" if delta>=D(".01") else "aversive" if delta<=D("-.01") else "none"
                frame=market_frame(market,adapter)
                art=journal.artifact(frame_png(frame),".png")
                before_state=brain.state_fingerprint()
                neural=brain.observe(frame,reinforcement)
                after_state=brain.state_fingerprint()
                execution=guard.execute(account,neural,market,calibration_passed=policy["calibrationAccepted"])
                snapshot=account.snapshot(market["markPrice"])
                body={"kind":"observation","runId":manifest["runId"],"sequence":seq,"wallTime":int(time.time()*1000),
                      "market":market,"input":art,"previousState":before_state,"nextState":after_state,"neural":neural,"neuralFingerprint":output_fingerprint(neural),
                      "reinforcement":reinforcement,"reinforcementPnlDelta":str(delta),"reinforcementAnchor":str(equity),
                      "execution":execution,"account":snapshot,"policyHash":digest(policy),"mode":"shadow",
                      "accountCapitalFlow":"none"}
                if seq%policy["checkpointEvery"]==0:body["checkpoint"]=checkpoint(brain,journal,"periodic")
                row=journal.append(body);rows.append(row);observations.append(body)
                anchor=equity
                atomic(directory/"latest.json",canonical(row))
                print(json.dumps({"sequence":seq,"side":neural["side"],"differenceHz":neural["difference_hz"],
                                  "execution":execution["status"],"root":row["root"],"computeSeconds":neural["compute_seconds"]}),flush=True)
            except (OSError,ValueError,KeyError,TimeoutError) as error:
                # Market/IO problems are recorded; unsafe continuation after brain advance is refused.
                atomic(directory/"fault.json",canonical({"at":int(time.time()*1000),"type":type(error).__name__,"afterSequence":len(rows)}))
                raise
            count+=1
            if (steps and count>=steps) or (replay_markets and len(rows)>=len(replay_markets)):break
            while not replay_markets and time.monotonic()-start<interval:
                if (directory/"STOP").exists():return
                time.sleep(min(1,interval-(time.monotonic()-start)))
    finally:
        journal.close();lock.close()

def replay(directory):
    journal=Journal(directory,readonly=True)
    try:
        audit=journal.audit()
        manifest=journal.meta("manifest")
        brain=FullBrain(learning=manifest["policy"]["modelLearning"])
        if brain.identity()!=manifest["model"]:raise ValueError("Replay environment or source mismatch")
        if manifest.get("runtimeSource")!=runtime_manifest(ROOT):raise ValueError("Replay runtime source mismatch; use archived release")
        verify_calibration(ROOT/manifest["policy"]["calibrationReport"],brain.identity(),manifest["policy"]["calibrationReportSha256"])
        brain.restore(journal.artifact_path(manifest["genesis"]["name"]))
        comparisons=[]
        account=ShadowAccount(manifest["shadowCapitalUsdc"])
        guard=ShadowGuard(manifest["policy"])
        anchor=account.principal
        for row in journal.rows():
            b=row["body"]
            if b.get("kind")!="observation":continue
            frame=read_frame(journal.artifact_path(b["input"]["name"]))
            import numpy as np
            if not np.array_equal(frame,market_frame(b["market"],manifest["adapter"])):raise ValueError("Sensory input mismatch")
            account.mark(b["market"])
            equity=account.equity(b["market"]["markPrice"])
            delta=equity-anchor
            kind="reward" if delta>=D(".01") else "aversive" if delta<=D("-.01") else "none"
            if kind!=b["reinforcement"] or str(delta)!=b["reinforcementPnlDelta"]:raise ValueError("Reward accounting mismatch")
            if brain.state_fingerprint()!=b["previousState"]:raise ValueError("Previous neural state mismatch")
            actual=brain.observe(frame,kind)
            if brain.state_fingerprint()!=b["nextState"]:raise ValueError("Next neural state mismatch")
            if output_fingerprint(actual)!=b["neuralFingerprint"]:raise ValueError("Neural replay mismatch at "+str(row["seq"]))
            execution=guard.execute(account,actual,b["market"],calibration_passed=manifest["policy"]["calibrationAccepted"])
            if execution!=b["execution"] or account.snapshot(b["market"]["markPrice"])!=b["account"]:raise ValueError("Shadow account replay mismatch")
            if str(equity)!=b["reinforcementAnchor"]:raise ValueError("Anchor mismatch")
            anchor=equity
            comparisons.append(row["seq"])
        result={"schema":"flyterm-replay/v1","runId":manifest["runId"],"head":audit["head"],
                "verifiedThrough":audit["rounds"],"matchingNeuralRounds":len(comparisons),
                "verified":True,"method":"full retained connectome replay on this host",
                "zeroKnowledgeProof":False,"crossMachineVerified":False,"at":int(time.time()*1000)}
        atomic(Path(directory)/"replay.json",canonical(result))
        print(json.dumps(result,indent=2),flush=True)
        return result
    finally:journal.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    r=sub.add_parser("run");r.add_argument("--out",type=Path,default=ROOT/"runs/hyper-shadow");r.add_argument("--steps",type=int,default=0);r.add_argument("--interval",type=float,default=60);r.add_argument("--adapter",choices=["upstream","contrast","movement"],default="movement");r.add_argument("--market-replay",type=Path)
    v=sub.add_parser("replay");v.add_argument("--out",type=Path,default=ROOT/"runs/hyper-shadow")
    args=parser.parse_args()
    if args.command=="run":run(args.out,args.steps,args.interval,args.adapter,args.market_replay)
    else:replay(args.out)
