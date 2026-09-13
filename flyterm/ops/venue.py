"""Public Hyperliquid evidence collector. unknownOid is never a terminal order."""
import json,time,urllib.request
from decimal import Decimal,ROUND_CEILING
from .codec import units,address,object_hash
TERMINAL={"filled":1,"canceled":2,"marginCanceled":2,"vaultWithdrawalCanceled":2,"openInterestCapCanceled":2,
          "selfTradeCanceled":2,"reduceOnlyCanceled":2,"siblingFilledCanceled":2,"delistedCanceled":2,
          "liquidatedCanceled":2,"scheduledCancel":2,"iocCancel":2,"rejected":3,"expired":4}
TERMINAL.update({name:3 for name in ("tickRejected","minTradeNtlRejected","perpMarginRejected","reduceOnlyRejected","badAloPxRejected","iocCancelRejected","badTriggerPxRejected","marketOrderNoLiquidityRejected","positionIncreaseAtOpenInterestCapRejected","positionFlipAtOpenInterestCapRejected","tooAggressiveAtOpenInterestCapRejected","openInterestIncreaseRejected","insufficientSpotBalanceRejected","oracleRejected","perpMaxPositionRejected")})
class EvidenceIncomplete(RuntimeError):pass
class Venue:
    def __init__(self,base="https://api.hyperliquid.xyz",transport=None):self.base=base;self.transport=transport
    def info(self,payload):
        if self.transport:return self.transport(payload)
        req=urllib.request.Request(self.base+"/info",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read(4_000_000))
        except Exception:raise EvidenceIncomplete("Venue data unavailable") from None
    def fills(self,user,start_ms,end_ms):
        seen={};cursor=start_ms
        for _ in range(8):
            page=self.info({"type":"userFillsByTime","user":address(user),"startTime":cursor,"endTime":end_ms,"aggregateByTime":False})
            if not isinstance(page,list):raise EvidenceIncomplete("Invalid fill page")
            added=0
            for f in page:
                if "tid" not in f or "time" not in f:raise EvidenceIncomplete("Fill identity missing")
                if not start_ms<=int(f["time"])<=end_ms:raise EvidenceIncomplete("Fill time outside request")
                key=str(f["tid"])
                if key in seen:
                    if seen[key]!=f:raise EvidenceIncomplete("Conflicting fill identity")
                else:seen[key]=f;added+=1
            if len(page)<2000:return sorted(seen.values(),key=lambda f:(int(f["time"]),str(f["tid"])))
            next_cursor=max(int(f["time"]) for f in page)
            if next_cursor<cursor or (next_cursor==cursor and added==0):raise EvidenceIncomplete("Fill pagination did not advance")
            cursor=next_cursor
        raise EvidenceIncomplete("Fill pagination budget reached")
    def terminal(self,user,cloid,expected_size_e8,buy,sent_ms,now_ms=None):
        now_ms=int(time.time()*1000) if now_ms is None else int(now_ms)
        status=self.info({"type":"orderStatus","user":address(user),"oid":cloid})
        if status.get("status")!="order":raise EvidenceIncomplete("Order not found or not terminal")
        wrapper=status.get("order",{});state=wrapper.get("status");order=wrapper.get("order",{})
        if state not in TERMINAL:raise EvidenceIncomplete("Order is not in a recognized terminal state")
        if order.get("coin")!="BTC" or order.get("side")!=("B" if buy else "A") or str(order.get("cloid") or "").lower()!=cloid.lower():raise EvidenceIncomplete("Order identity mismatch")
        if units(order.get("origSz"),8)!=expected_size_e8:raise EvidenceIncomplete("Original order size mismatch")
        terminal_ms=int(wrapper["statusTimestamp"])
        if not sent_ms<=terminal_ms<=now_ms+2000:raise EvidenceIncomplete("Terminal timestamp mismatch")
        fills=[f for f in self.fills(user,max(0,sent_ms-1000),min(now_ms+2000,terminal_ms+2000)) if int(f["oid"])==int(order["oid"])]
        total=Decimal(0);value=Decimal(0);pnl=Decimal(0);fee=Decimal(0)
        for f in fills:
            if f["coin"]!="BTC" or f["side"]!=order["side"] or f.get("feeToken")!="USDC":raise EvidenceIncomplete("Fill asset/side/fee mismatch")
            n=Decimal(f["sz"]);px=Decimal(f["px"]);charge=Decimal(f["fee"])
            if not all(x.is_finite() for x in (n,px,charge)) or n<=0 or px<=0 or charge<0:raise EvidenceIncomplete("Unsupported fill quantity or rebate")
            total+=n;value+=n*px;pnl+=Decimal(f["closedPnl"]);fee+=charge
        size=units(total,8)
        if size>expected_size_e8 or (state=="filled" and size!=expected_size_e8):raise EvidenceIncomplete("Fills do not establish terminal execution")
        if TERMINAL[state]==3 and size:raise EvidenceIncomplete("Rejected order has fills")
        if not size and (fee or pnl):raise EvidenceIncomplete("Empty fill has accounting values")
        receipt={"status":TERMINAL[state],"filledE8":size,"averagePriceE8":units(value/total,8) if total else 0,
                 "closedPnlE6":units(pnl,6),"feeE6":units(fee,6,ROUND_CEILING)}
        evidence={"kind":"hyper-order-terminal","user":address(user),"cloid":cloid,"status":status,"fills":fills,"retrievedAt":now_ms}
        return receipt,evidence,"0x"+object_hash(evidence)
