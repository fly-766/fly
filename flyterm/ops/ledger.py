"""Bounded positive ledger evidence for balance contamination.
Schema reference: nktkas/hyperliquid db80d598f6e4672edc090fe69994ecec97ebc980
userNonFundingLedgerUpdates, mapped to the official Hyperliquid info endpoint.
Unknown/new schemas fail closed. A match is venue evidence, not a consensus proof.
"""
from .codec import units,address,raw
from .venue import EvidenceIncomplete
def matching(venue,user,start_ms,end_ms,kind,amount,*,sender=None,destination=None,source_dex=None,deposit_wallet=None):
    rows=venue.info({"type":"userNonFundingLedgerUpdates","user":address(user),"startTime":max(0,start_ms),"endTime":end_ms})
    if not isinstance(rows,list) or len(rows)>=500:raise EvidenceIncomplete("Ledger window incomplete or too large")
    found={}
    for row in rows:
        if not start_ms<=int(row.get("time",-1))<=end_ms:continue
        raw(row.get("hash",""),32);d=row.get("delta",{});t=d.get("type");net=None;fee=0
        if kind=="CLASS" and t=="accountClassTransfer" and d.get("toPerp") is True and units(d.get("usdc"),6)==amount:net=amount
        elif kind=="DEPOSIT":
            if t=="deposit" and 0<amount-units(d.get("usdc"),6)<=2_000_000:net=units(d["usdc"],6);fee=amount-net
            elif t=="deposit" and units(d.get("usdc"),6)==amount:net=amount
            elif t in ("send","spotTransfer") and d.get("token")=="USDC" and str(d.get("destination","")).lower()==user.lower():
                allowed={str(deposit_wallet).lower(),"0x2000000000000000000000000000000000000000"}
                if str(d.get("user","")).lower() in allowed and units(d.get("amount"),6)==amount and units(d.get("fee","0"),6)==0:net=amount
        elif kind=="EXIT" and t=="send":
            if d.get("token")=="USDC" and str(d.get("user","")).lower()==str(sender).lower() and str(d.get("destination","")).lower()==str(destination).lower() and d.get("sourceDex")==source_dex and d.get("destinationDex")=="spot" and units(d.get("amount"),6)==amount:
                # Standard pre-activated sends have no USDC transfer fee. A fee plus unrelated
                # balance changes needs explicit investigation rather than guessing its allocation.
                if units(d.get("fee","0"),6)==0:net=amount
        if net is not None:
            key=(row["hash"],row["time"])
            if key in found and found[key][2]!=row:raise EvidenceIncomplete("Conflicting ledger identity")
            found[key]=(net,fee,row)
    if len(found)!=1:raise EvidenceIncomplete("No unique matching transfer ledger record")
    return next(iter(found.values()))
