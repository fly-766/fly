"""One durable keeper for the two fixed routes. Plan is the default; live requires exact approval."""
import fcntl,json,os,time
from pathlib import Path
from eth_utils import keccak
from flyterm.errors import ObserverRestartRequired
from .rpc import Rpc
from .state import Snapshot
from .executor import Executor,NotArmed
from .journal import OperationJournal
from .codec import object_hash,raw
from .planner import hyper_step,xlayer_step,action,neural_actionable
from .settler import collect
from .funding import next_funding
from .certificates import typed,sign,settlement_call,commit_call
from .venue import Venue,EvidenceIncomplete
from .cctp import Cctp
from .bridges import BridgeIndex
class Keeper:
    def __init__(self,config,directory,*,live=False,approved=None,brain=None):
        self.config=config;self.live=live;self.brain=brain
        if live and (not config["liveEnabled"] or not config.get("mainnetCanaryAccepted") or approved!=object_hash(config)):raise NotArmed("Exact live profile and separately accepted canary required")
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700);self.directory=directory
        self.lock=(directory/"keeper.lock").open("ab");fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.j=OperationJournal(directory/"operations.sqlite");self.index=BridgeIndex(self.j)
        self.rpcs={n:Rpc(os.environ.get(c["rpcEnv"]),c["chainId"]) for n,c in config["chains"].items()}
        for name,rpc in self.rpcs.items():
            rpc.verify_chain();c=config["chains"][name]
            if live:
                if not c["liveEnabled"]:raise NotArmed("Per-chain profile disabled")
        self.executors={n:Executor(c,self.j,self.rpcs[n]) for n,c in config["chains"].items()}
        if live:
            for executor in self.executors.values():executor.verify_code_pins()
            x=config["chains"]["xlayer"]
            if not config.get("localFixtureOnly"):
                if not x.get("creatorIncome",{}).get("vault"):raise NotArmed("Production tax vault not configured")
                snapshot=Snapshot(self.rpcs["xlayer"])
                for name in ("converter","buyback"):
                    if snapshot.get(x["addresses"][name],"hopExecutor()",["address"]).lower()!=x["signerAddress"].lower():raise NotArmed("Hop operator identity mismatch")
        self.venue=Venue();self.cctp=Cctp()
        from .hop import OkxQuotes
        self.quotes=OkxQuotes()
    def close(self):self.j.close();self.lock.close()
    def _key(self,env):
        name=self.config[env];p=os.environ.get(name)
        if not p:raise NotArmed("Certificate signing file unavailable")
        try:return Path(p).read_text().strip()
        except Exception:raise NotArmed("Certificate signing file unavailable") from None
    def _submit(self,chain,plan):
        c=self.config["chains"][chain]
        # Identical calldata can be a NEW claim/deposit/buyback in a later state.
        # Only retries of the same saved operation reuse its id and signed bytes.
        intent=dict(plan["intent"])
        if "creatorClaimTx" not in intent:intent["operationContext"]=self.snapshots[chain].block["hash"]
        out=self.executors[chain].submit(plan["kind"],intent,live=self.live,approved_hash=object_hash(c))
        if "evidence" in plan:self.j.save_evidence(plan["evidence"])
        return {"chain":chain,"kind":plan["kind"],**out}
    def _certificate(self,snap,cfg,cert):
        doc=typed("Settlement",cfg["chainId"],cfg["addresses"]["settlement"],cert["message"]);self.j.save_evidence(cert["evidence"])
        if not self.live:return {"chain":"hyper","kind":cert["action"],"state":"CERTIFICATE_PLAN","typedData":doc,"evidenceHash":cert["message"]["evidence"],"signingEnabled":False}
        sig=sign(doc,self._key("settlementKeyFileEnv"),self.config["settlementSigner"])
        m=cert["message"];data=settlement_call(cert["action"],cert["values"],m["coreBlock"],m["deadline"],m["evidence"],sig,cfg.get("accountVersion",3))
        return self._submit("hyper",{"kind":cert["action"],"intent":{"chainId":cfg["chainId"],"to":cfg["addresses"]["account"],"value":"0","data":data},"evidence":cert["evidence"]})
    def step(self):
        # Uncertain transactions keep their nonce and calldata. No blind new submission.
        for chain,cfg in self.config["chains"].items():
            pending=self.j.pending(cfg["chainId"],cfg["signerAddress"])
            if pending:
                e=self.executors[chain]
                return {"chain":chain,**(e.resume(pending[0]["id"],approved_hash=object_hash(cfg)) if self.live else e.reconcile(pending[0]["id"]))}
        snapshots={n:Snapshot(r,account_version=self.config["chains"][n].get("accountVersion",3)) for n,r in self.rpcs.items()};self.snapshots=snapshots
        from .public import publish
        publish(self.directory,self.config,snapshots,self.j)
        now=int(time.time())
        stale=[n for n,snapshot in snapshots.items() if snapshot.rpc.chain_id in (196,999) and not -30<=now-snapshot.timestamp<=90]
        if stale:return {"state":"WAIT","reason":"stale_chain_snapshot","chains":stale}
        for route in self.config["routes"]:
            src=route["sourceChain"];dest=route["destinationChain"]
            self.index.scan(self.rpcs[src],route)
            plan=self.index.next(Snapshot(self.rpcs[dest],self.config["chains"][dest]["confirmations"]),route,self.cctp)
            if plan:return self._submit(dest,plan)
        cfg=self.config["chains"]["hyper"];snap=snapshots["hyper"]
        hplan=hyper_step(snap,cfg)
        if hplan.get("wait")=="venue_settlement":
            try:return self._certificate(snap,cfg,collect(snap,cfg,self.venue))
            except EvidenceIncomplete:return {"chain":"hyper","state":"WAIT","reason":"venue_evidence_incomplete"}
        if "intent" in hplan:return self._submit("hyper",hplan)
        funding=next_funding(Snapshot(self.rpcs["hyper"],cfg["confirmations"],cfg.get("accountVersion",3)),cfg,self.venue,self.j)
        if funding:return self._certificate(snap,cfg,funding)
        xcfg=dict(self.config["chains"]["xlayer"]);xcfg["localFixtureOnly"]=self.config.get("localFixtureOnly",False)
        from .creator import creator_step
        xcfg["allowNewCapital"]=hplan.get("wait")!="paused_or_recovery_only"
        cplan=creator_step(snapshots["xlayer"],xcfg,self.j) if xcfg["allowNewCapital"] else None
        if cplan:return self._submit("xlayer",cplan)
        xplan=xlayer_step(snapshots["xlayer"],xcfg,self.quotes)
        if "intent" in xplan:return self._submit("xlayer",xplan)
        if hplan.get("wait")!="model_observation" or not self.brain:return {"state":"WAIT","hyper":hplan.get("wait"),"xlayer":xplan.get("wait")}
        state=hplan["snapshot"];reg=cfg["addresses"]["registry"];nonce=snap.get(reg,"nonce()",["uint64"]);side=snap.get(reg,"side()",["uint8"])
        actionable=neural_actionable(side,state,cfg,snap.timestamp)
        if nonce>state["lastCommit"] and snap.get(reg,"deadline()",["uint64"])>=snap.timestamp and actionable:
            return self._submit("hyper",action(cfg["chainId"],cfg["addresses"]["account"],"execute(uint64)",["uint64"],[nonce],"model_execute"))
        self.brain.observe(state)
        message=self.brain.commit(snap,cfg)
        if message is None:return {"state":"WAIT","reason":"next_completed_market_bar"}
        side=message["side"];actionable=neural_actionable(side,state,cfg,snap.timestamp)
        if not actionable and message["toRound"]-message["fromRound"]+1<cfg["anchorEveryRounds"]:return {"state":"OBSERVED","round":message["toRound"],"side":side}
        doc=typed("Commit",cfg["chainId"],reg,message)
        if not self.live:return {"state":"COMMIT_PLAN","typedData":doc,"signingEnabled":False}
        sig=sign(doc,self._key("modelKeyFileEnv"),self.config["modelSigner"])
        return self._submit("hyper",{"kind":"model_commit","intent":{"chainId":cfg["chainId"],"to":reg,"value":"0","data":commit_call(message,sig)}})
    def run(self,steps=0):
        count=0
        while not steps or count<steps:
            if (self.directory/"STOP").exists():break
            try:out=self.step()
            except Exception as error:
                # Do not emit raw provider responses, URLs or signing errors.
                out={"state":"WAIT_OR_FAULT","errorType":type(error).__name__}
                if isinstance(error,ObserverRestartRequired):
                    from flyterm.records import atomic,canonical
                    atomic(self.directory/"health.json",canonical({"state":"RESTART_REQUIRED","errorType":type(error).__name__,"at":int(time.time()*1000),"liveEnabled":self.live}))
                    raise
            out["at"]=int(time.time()*1000);out["liveEnabled"]=self.live
            from flyterm.records import atomic,canonical
            atomic(self.directory/"health.json",canonical(out))
            print(json.dumps({k:v for k,v in out.items() if k!="typedData"},ensure_ascii=False),flush=True)
            count+=1
            if steps and count>=steps:break
            time.sleep(10)
