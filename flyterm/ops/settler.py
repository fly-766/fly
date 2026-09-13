"""Fail-closed certificates from public venue evidence plus a consistent native-state snapshot.
These are operator attestations, not trustless proofs. Unknown operations stay pending.
"""
from .codec import object_hash,address,units
from .certificates import payload,order_tuple,ORDER_TYPE
from .venue import EvidenceIncomplete
from .ledger import matching as match_ledger
def collect(snapshot,config,venue):
    a=address(config["addresses"]["account"]);reader=config["addresses"]["reader"]
    s=snapshot.account(a,reader);core=s["core"]
    if not s["pending"] or core["coreBlock"]<=s["sentCoreBlock"]:raise EvidenceIncomplete("No advanced pending operation")
    evidence={"schema":"flyterm-venue-evidence/v1","account":a,"snapshot":s,"raw":[],"feeEvidence":"USDC net shortfall checked against native balances; protocol fee attribution is not a computation proof"}
    amount=s["pendingAmount"];kind=s["pending"]
    if kind==5:
        users=[a,config["addresses"]["profitExit"],config["addresses"]["recoveryExit"]]
        modes=[venue.info({"type":"userAbstraction","user":address(u)}) for u in users]
        if any(x!="disabled" for x in modes):raise EvidenceIncomplete("All three Core accounts must report disabled abstraction")
        evidence["raw"]=list(zip(users,modes));action="settleSetup";values={}
        h=payload("SETUP_DISABLED",["address","address"],users[1:])
    elif kind==1:
        delta=s["spot"]["balanceE8"]-s["spotBeforeE8"]
        if not core["exists"] or core["quantity"] or delta<=0:raise EvidenceIncomplete("Deposit balance not settled")
        credited=delta//100;fee=amount-credited
        if delta%100 or not 0<=fee<=2_000_000:
            credited,fee,event=match_ledger(venue,a,s["sentAt"]*1000,snapshot.timestamp*1000,"DEPOSIT",amount,deposit_wallet=config.get("protocol",{}).get("depositWallet"))
            if delta<credited*100:raise EvidenceIncomplete("Ledger credit not covered by native balance")
            evidence["raw"]=[event];evidence["balanceContamination"]="Extra balance is not credited as new principal"

        action="settleDeposit";values={"creditedE6":credited,"feeE6":fee};h=payload("DEPOSIT",["uint64","uint64"],[credited,fee])
    elif kind==4:
        credited=core["cashE6"]-s["cashBefore"];fee=amount-credited
        clean=not core["quantity"] and s["spot"]["balanceE8"]+amount*100==s["spotBeforeE8"] and credited>0 and 0<=fee<=2_000_000
        if not clean:
            credited,fee,event=match_ledger(venue,a,s["sentAt"]*1000,snapshot.timestamp*1000,"CLASS",amount)
            if core["quantity"] or core["cashE6"]<s["cashBefore"]+credited or s["spot"]["balanceE8"]+amount*100<s["spotBeforeE8"]:raise EvidenceIncomplete("Ledger class transfer not covered")
            evidence["raw"]=[event];evidence["balanceContamination"]="Matching class transfer required; extra balances stay unallocated"

        action="settleClassTransfer";values={"creditedE6":credited,"feeE6":fee};h=payload("CLASS_TRANSFER",["uint64","uint64"],[credited,fee])
    elif kind==2:
        cloid="0x"+s["cloid"].to_bytes(16,"big").hex()
        values,order_evidence,_=venue.terminal(a,cloid,amount,s["pendingBuy"],s["sentAt"]*1000)
        final=core["quantity"]*10**(8-core["sizeDecimals"])
        expected=s.get("positionBeforeSignedE8",s["positionBeforeE8"])+(values["filledE8"] if s["pendingBuy"] else -values["filledE8"])
        if final!=expected or core["isolated"]:raise EvidenceIncomplete("Terminal fill/native position disagree")
        values["finalPositionE8"]=final;evidence["raw"]=[order_evidence];action="settleOrder"
        from .certificates import order_type
        version=config.get("accountVersion",3)
        h=payload("ORDER_V05" if version>=5 else "ORDER",["uint128",order_type(version)],[s["cloid"],order_tuple(values)])
    elif kind==3:
        dest=config["addresses"]["recoveryExit" if s["exitKind"]==2 else "profitExit"]
        before=snapshot.get(dest,"coreBefore()",["uint256"]);spot=snapshot.spot(reader,dest);delta=spot["balanceE8"]-before
        if delta<=0:raise EvidenceIncomplete("Exit credit incomplete")
        net=delta//100;fee=amount-net
        debited=(s["spot"]["balanceE8"]+amount*100==s["spotBeforeE8"]) if s["positionBeforeE8"]==2**64-1 else (core["cashE6"]==s["cashBefore"]-amount)
        clean=not core["quantity"] and debited and delta%100==0 and 0<=fee<=2_000_000 and spot["balanceE8"]-spot["holdE8"]>=net*100
        if not clean:
            from_spot=s["positionBeforeE8"]==2**64-1
            net,fee,event=match_ledger(venue,a,s["sentAt"]*1000,snapshot.timestamp*1000,"EXIT",amount,sender=a,destination=dest,source_dex="spot" if from_spot else "")
            covered=(s["spot"]["balanceE8"]+amount*100>=s["spotBeforeE8"]) if from_spot else (core["cashE6"]>=s["cashBefore"]-amount)
            if core["quantity"] or not covered or delta<net*100 or spot["balanceE8"]-spot["holdE8"]<net*100:raise EvidenceIncomplete("Ledger exit not covered")
            evidence["raw"]=[event];evidence["balanceContamination"]="Matching outbound ledger transfer required"

        action="settleExit";values={"netE6":net,"feeE6":fee};h=payload("EXIT",["uint64","uint64"],[net,fee])
        evidence["raw"].append({"exit":address(dest),"spot":spot,"beforeE8":before})
    else:raise EvidenceIncomplete("Unsupported pending kind")
    return {"action":action,"values":values,"message":{"account":a,"operation":s["operation"],"payload":h,"coreBlock":core["coreBlock"],
             "deadline":snapshot.timestamp+120,"evidence":"0x"+object_hash(evidence)},"evidence":evidence}
