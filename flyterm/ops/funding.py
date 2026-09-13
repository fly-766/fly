"""Funding events are signed once, using stable identity and bounded overlapping pagination."""
from .codec import object_hash,units,raw
from .certificates import payload
from .venue import EvidenceIncomplete
def next_funding(snap,cfg,venue,journal=None):
    a=cfg["addresses"]["account"];baseline=int(cfg["fundingFromMs"]);cursor=baseline
    key=object_hash({"account":a.lower(),"chain":cfg["chainId"],"baseline":baseline})
    if journal:
        journal.db.execute("CREATE TABLE IF NOT EXISTS funding_cursor(id TEXT PRIMARY KEY,at INTEGER NOT NULL)")
        prior=journal.db.execute("SELECT at FROM funding_cursor WHERE id=?",(key,)).fetchone()
        if prior:cursor=max(baseline,prior[0]-86400000)
    for _ in range(8):
        rows=venue.info({"type":"userFunding","user":a,"startTime":cursor,"endTime":snap.timestamp*1000})
        if not isinstance(rows,list) or len(rows)>2000:raise EvidenceIncomplete("Invalid funding page")
        if not rows:return None
        rows=sorted(rows,key=lambda x:(x["time"],x["hash"]))
        for r in rows:
            if not cursor<=int(r["time"])<=snap.timestamp*1000:raise EvidenceIncomplete("Funding timestamp outside request")
            d=r["delta"]
            if d.get("type")!="funding" or d.get("coin")!="BTC":continue
            id="0x"+object_hash({"account":a.lower(),"time":r["time"],"hash":r["hash"],"delta":d})
            if snap.get(a,"bookedEvents(bytes32)",["bool"],["bytes32"],[raw(id,32)]):continue
            delta=units(d["usdc"],6);evidence={"schema":"flyterm-funding/v03","account":a,"event":r};core=snap.core(cfg["addresses"]["reader"],a)
            return {"action":"bookCost","values":{"id":id,"delta":delta,"trading":True},"message":{"account":a,"operation":id,"payload":payload("COST",["int256","bool"],[delta,True]),"coreBlock":core["coreBlock"],"deadline":snap.timestamp+120,"evidence":"0x"+object_hash(evidence)},"evidence":evidence}
        last=int(rows[-1]["time"])
        if journal:
            with journal.db:journal.db.execute("INSERT OR REPLACE INTO funding_cursor VALUES (?,?)",(key,last))
        if len(rows)<500:return None
        if last<=cursor:raise EvidenceIncomplete("Funding page did not advance")
        cursor=last
    raise EvidenceIncomplete("Funding pagination budget reached")
