"""Explicit public projection; never expose signer paths, URLs or raw transaction journals."""
from flyterm.records import atomic,canonical
def publish(directory,config,snapshots,journal):
    a=config["chains"]["hyper"]["addresses"];h=snapshots["hyper"];x=snapshots["xlayer"];s=h.account(a["account"],a["reader"])
    fields={"nativeBudget":"uint256","quoteBudget":"uint256","escrowedTokens":"uint256","totalTokensSentDead":"uint256"}
    funds={k:str(x.get(a["buyback"],k+"()",[t])) for k,t in fields.items()}
    funds.update(costBasisE6=str(s["costBasisE6"]),tradingNetE6=str(s["tradingNetE6"]),operatingCostE6=str(s["operatingCostE6"]),availableProfitE6=str(s["availableProfit"]),equityE6=str(s["core"]["equityE6"]))
    reg=a["registry"]
    ops=[]
    for r in journal.db.execute("SELECT id,kind,state,chain,created,receipt FROM ops ORDER BY created DESC,rowid DESC LIMIT 20"):
        import json
        receipt=json.loads(r["receipt"]) if r["receipt"] else {}
        ops.append({"id":r["id"],"kind":r["kind"],"state":r["state"],"chainId":r["chain"],"at":r["created"],"transactionHash":receipt.get("transactionHash")})
    out={"schema":"flyterm-public-operations/v03","ok":True,"deployment":"configured","at":min(h.timestamp,x.timestamp)*1000,"chainTimes":{"hyper":h.timestamp*1000,"xlayer":x.timestamp*1000},
        "liveEnabled":config["liveEnabled"],"projectToken":config["chains"]["xlayer"]["projectToken"],"addresses":a,"funds":funds,"pendingKind":s["pending"],"paused":s["paused"],
        "onchain":{"chainId":h.rpc.chain_id,"block":h.tag,"blockHash":h.block["hash"],"registry":reg,"runId":"0x"+h.get(reg,"runId()",["bytes32"]).hex(),"lastRound":h.get(reg,"lastRound()",["uint64"]),
                   "recordRoot":"0x"+h.get(reg,"recordRoot()",["bytes32"]).hex(),"stateRoot":"0x"+h.get(reg,"stateRoot()",["bytes32"]).hex()},
        "trust":"open computation and signed venue attestations; not a ZK proof","operations":ops}
    if s.get("accountVersion",3)>=5:
        q=s["core"]["quantity"]*10**(8-s["core"]["sizeDecimals"])
        out["position"]={"quantityE8":str(q),"side":"SHORT" if q<0 else "LONG" if q>0 else "FLAT"}
        out["riskControls"]={"accountVersion":5,"maxEntryLeverage":s["leverageCap"],"entryReserveBps":s["reserveBps"],"shortEnabled":s["shortEnabled"],"maxOrderE6":str(s["maxOrderE6"]),"lossStopE6":str(s["lossStopE6"]),"marginMode":"cross; dedicated contract account"}
    atomic(directory/"public.json",canonical(out))
