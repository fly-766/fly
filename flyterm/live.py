"""Full-model observer for an actual contract account. Realized venue ledger drives feedback.
Observation is keyless. Publication/execution belongs to the separately armed keeper.
"""
import fcntl,json,time,uuid
from pathlib import Path
from .errors import ObserverRestartRequired
from .neural import FullBrain,market_frame,frame_png,output_fingerprint,read_frame
from .records import Journal,canonical,atomic,digest,file_digest
from .worker import checkpoint,restore_committed
from .calibration import verify as verify_calibration
from market import fetch_market
ROOT=Path(__file__).resolve().parents[1]
def sources():
    paths=[ROOT/"market.py",ROOT/"policy.json",*sorted((ROOT/"flyterm").rglob("*.py"))]
    return {str(p.relative_to(ROOT)):file_digest(p) for p in paths}
class LiveBrain:
    def __init__(self,directory,policy_path=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=(self.directory/"worker.lock").open("ab")
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.j=Journal(directory);policy=json.loads(Path(policy_path or ROOT/"policy.json").read_text())
        self.brain=FullBrain(learning=policy["modelLearning"]);identity=self.brain.identity()
        calibration=verify_calibration(ROOT/policy["calibrationReport"],identity,policy["calibrationReportSha256"])
        m=self.j.meta("manifest")
        if m:
            if m["model"]!=identity or m["runtimeSource"]!=sources() or m["policy"]!=policy:raise ValueError("Live run identity changed")
            self.j.audit();self.rows=restore_committed(self.brain,self.j)
        else:
            genesis=checkpoint(self.brain,self.j,"genesis")
            m={"schema":"flyterm-contract-observer/v03","runId":str(uuid.uuid4()),"createdAt":int(time.time()*1000),"model":identity,"policy":policy,"runtimeSource":sources(),
               "adapter":"movement","genesis":genesis,"genesisState":self.brain.state_fingerprint(),"mode":"contract-observer",
               "feedback":"settled tradingNetE6 minus booked operatingCostE6; no simulated fills","calibration":calibration}
            self.j.initialize(m);atomic(self.directory/"manifest.json",canonical(m));self.rows=[]
            import shutil
            for rel in set(m["runtimeSource"])|set(identity["source"]):
                dst=self.directory/"source"/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,dst)
        self.manifest=m;self._usable=True
    def close(self):self.j.close();self.lock.close()
    def observe(self,snapshot,market=None):
        if not self._usable:raise ObserverRestartRequired("Reload the last committed model state")
        if snapshot["pending"] or snapshot["nativePrincipalE6"] or snapshot["unallocatedSpotE6"]:raise ValueError("Settle account before observation")
        market=market or fetch_market()
        bars=[c for c in market["candles"] if c["closeTime"]<=market["providerTime"]*1000]
        if len(bars)<62 or any(b["time"]-a["time"]!=60000 for a,b in zip(bars[-62:],bars[-61:])):raise ValueError("Sensory market gaps")
        if self.rows:
            prev=self.rows[-1]["body"]
            if bars[-1]["closeTime"]<=prev["completedBar"]:return None
            anchor=prev["reinforcementAnchorE6"]
        else:anchor=0
        cumulative=snapshot["tradingNetE6"]-snapshot["operatingCostE6"];delta=cumulative-anchor
        feedback="reward" if delta>=10000 else "aversive" if delta<=-10000 else "none"
        seq=len(self.rows)+1;frame=market_frame(market,"movement");art=self.j.artifact(frame_png(frame),".png")
        self._usable=False
        try:
            before=self.brain.state_fingerprint();out=self.brain.observe(frame,feedback);after=self.brain.state_fingerprint()
            body={"kind":"observation","runId":self.manifest["runId"],"sequence":seq,"wallTime":int(time.time()*1000),"completedBar":bars[-1]["closeTime"],
                  "market":market,"input":art,"previousState":before,"nextState":after,"neural":out,"neuralFingerprint":output_fingerprint(out),
                  "reinforcement":feedback,"reinforcementDeltaE6":delta,"reinforcementAnchorE6":cumulative,
                  "contractSnapshot":snapshot,"execution":{"status":"PROPOSAL_ONLY"},"mode":"contract-observer"}
            if seq%8==0:body["checkpoint"]=checkpoint(self.brain,self.j,"periodic")
            row=self.j.append(body);self.rows.append(row);atomic(self.directory/"latest.json",canonical(row));self._usable=True;return row
        except Exception:
            raise ObserverRestartRequired("Model step could not be durably recorded; restart required") from None
    def commit(self,snap,config):
        registry=config["addresses"]["registry"];m=self.manifest
        if not self.rows:return None
        last=snap.get(registry,"lastRound()",["uint64"])
        if last>=len(self.rows):return None
        row=self.rows[-1];b=row["body"];first=self.rows[last]
        observed=int(b["market"]["providerTime"]);deadline=observed+90
        if not observed<=snap.timestamp<=deadline:return None
        if len(self.rows)-last>1024:raise ValueError("Run is too far ahead of onchain registry")
        message={"runId":"0x"+digest(m["runId"]),"modelHash":"0x"+digest(m["model"]),"nonce":snap.get(registry,"nonce()",["uint64"])+1,
                 "fromRound":last+1,"toRound":row["seq"],"observedAt":observed,"deadline":deadline,
                 "referencePriceE8":int(round(b["market"]["markPrice"]*1e8)),"previousRecord":"0x"+first["previous"],"record":"0x"+row["root"],
                 "previousState":"0x"+first["body"]["previousState"],"nextState":"0x"+b["nextState"],"inputHash":"0x"+b["input"]["sha256"],
                 "side":{"HOLD":0,"BUY":1,"SELL":2}[b["neural"]["side"]]}
        for field,key in [("recordRoot","previousRecord"),("stateRoot","previousState"),("runId","runId"),("modelHash","modelHash")]:
            actual="0x"+snap.get(registry,field+"()",["bytes32"]).hex()
            if actual.lower()!=message[key].lower():raise ValueError("Onchain registry/run continuity mismatch")
        return message
def replay(directory):
    j=Journal(directory,readonly=True)
    try:
        audit=j.audit();m=j.meta("manifest");brain=FullBrain(learning=m["policy"]["modelLearning"])
        if brain.identity()!=m["model"] or sources()!=m["runtimeSource"]:raise ValueError("Use this run's exact source environment")
        brain.restore(j.artifact_path(m["genesis"]["name"]));anchor=0
        import numpy as np
        for row in j.rows():
            b=row["body"];snap=b["contractSnapshot"];current=snap["tradingNetE6"]-snap["operatingCostE6"];delta=current-anchor
            feedback="reward" if delta>=10000 else "aversive" if delta<=-10000 else "none"
            if delta!=b["reinforcementDeltaE6"] or feedback!=b["reinforcement"]:raise ValueError("Contract feedback mismatch")
            frame=market_frame(b["market"],"movement")
            if not np.array_equal(frame,read_frame(j.artifact_path(b["input"]["name"]))):raise ValueError("Pixels differ")
            if brain.state_fingerprint()!=b["previousState"]:raise ValueError("Previous model state differs")
            out=brain.observe(frame,feedback)
            if output_fingerprint(out)!=b["neuralFingerprint"] or brain.state_fingerprint()!=b["nextState"]:raise ValueError("Model replay differs")
            anchor=current
        result={"verified":True,"rounds":audit["rounds"],"head":audit["head"],"onchainEvidenceIndependentlyVerified":False,"computationProof":False}
        atomic(Path(directory)/"replay.json",canonical(result));return result
    finally:j.close()
