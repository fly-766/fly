"""Select at most one fixed-destination action from observed contract state."""
from .codec import calldata,address
def action(chain,to,signature,types=(),args=(),kind=None):
    return {"kind":kind or signature.split("(")[0],"intent":{"chainId":chain,"to":address(to),"value":"0","data":calldata(signature,list(types),list(args))}}
def hyper_step(snap,cfg):
    a=cfg["addresses"];at=a["account"];reader=a["reader"];chain=cfg["chainId"];s=snap.account(at,reader)
    if s["pending"]:return {"wait":"venue_settlement","snapshot":s}
    if not s["setupComplete"]:
        if all(snap.core(reader,u)["exists"] for u in (at,a["profitExit"],a["recoveryExit"])):return action(chain,at,"configureCore()")
        return {"wait":"core_gas_bootstrap_required","snapshot":s}
    # Continue both already-authorized return routes independently of new trading.
    for key in ("profitExit","recoveryExit"):
        exit=a[key];stage=snap.get(exit,"stage()",["uint8"])
        if stage==2:return action(chain,exit,"bridgeToEvm()",kind=key+"_to_evm")
        if stage==3:return action(chain,exit,"reconcileEvm()",kind=key+"_reconcile")
        if stage==4:
            n=snap.get(exit,"amount()",["uint256"]);fee=min(n*cfg["bridgeMaxFeeBps"]//10000,cfg["bridgeMaxFeeE6"])
            return action(chain,exit,"burnReturn(uint256)",["uint256"],[fee],key+"_burn")
    if s["paused"] or s["recoveryOnly"]:
        if s["core"]["quantity"]>0:return action(chain,at,"emergencyClose()")
        return {"wait":"paused_or_recovery_only","snapshot":s}
    if s["core"]["equityE6"]+s["nativePrincipalE6"]+200_000_000<=s["costBasisE6"] and s["core"]["quantity"]>0:return action(chain,at,"emergencyClose()")
    if s["nativePrincipalE6"]>=2_000_000 and not s["core"]["quantity"]:return action(chain,at,"fund()")
    if s["unallocatedSpotE6"] and not s["core"]["quantity"]:return action(chain,at,"moveToPerp()")
    profit=s["availableProfit"]
    if profit>=cfg["minimumProfitE6"] and snap.get(a["profitExit"],"stage()",["uint8"])==0:
        return action(chain,at,"requestExit(uint256,bool)",["uint256","bool"],[min(profit,cfg["maxProfitBatchE6"]),False],"profit_request")
    return {"wait":"model_observation","snapshot":s}
def xlayer_step(snap,cfg):
    a=cfg["addresses"];p=cfg["protocol"];chain=cfg["chainId"];conv=a["converter"];buy=a["buyback"];treasury=a["treasury"];token=cfg["projectToken"]
    get=snap.get
    if cfg.get("withdrawConfirmedPrincipal") and get(a["recoveryVault"],"credited()",["uint256"])>0:
        return action(chain,a["recoveryVault"],"withdraw()",kind="principal_withdraw")
    if not get(conv,"paused()",["bool"]):
        vault=get(p["manager"],"vaultOf(address)",["address"],["address"],[token])
        if int(vault,16):
            if get(vault,"claimableNow(address)",["uint256"],["address"],[conv])>0:return action(chain,conv,"claim()",kind="tax_claim")
        quote=p.get("quote") or p.get("wgooglx") or p["usd0"]
        balance=get(quote,"balanceOf(address)",["uint256"],["address"],[conv])
        minimum=int(cfg.get("minimumQuoteWei") or cfg["minimumConversionE6"])
        if address(quote)==address(p["usd0"]):
            if balance>=cfg["minimumConversionE6"]:return action(chain,conv,"convert(uint256,uint256,bytes)",["uint256","uint256","bytes"],[min(balance,get(conv,"maxBatch()",["uint256"])),balance*99//100,b""],"tax_convert")
        elif balance>=minimum:
            from .hop import quote_to_usd0
            amount=min(balance,get(conv,"maxBatch()",["uint256"]))
            min_usd0=max(amount//10**12*99//100,1)
            if not cfg.get("localFixtureOnly"):return {"wait":"okx_hop_quote_required"}
            hop=bytes.fromhex(quote_to_usd0(min_usd0)[2:])
            return action(chain,conv,"convert(uint256,uint256,bytes)",["uint256","uint256","bytes"],[amount,min_usd0,hop],"tax_convert")
    if not get(treasury,"paused()",["bool"]):
        balance=get(treasury,"liquidPrincipal()",["uint256"]);minimum=get(treasury,"minBatch()",["uint256"])
        if balance>=minimum:
            n=min(balance,get(treasury,"maxBatch()",["uint256"]));fee=min(n*cfg["bridgeMaxFeeBps"]//10000,cfg["bridgeMaxFeeE6"])
            return action(chain,treasury,"forward(uint256,uint256)",["uint256","uint256"],[n,fee],"principal_burn")
    if get(buy,"paused()",["bool"]):return {"wait":"buyback_paused"}
    native=get(buy,"nativeBudget()",["uint256"])
    if native>=cfg["minimumConversionE6"]:return action(chain,buy,"convertProfit(uint256)",["uint256"],[min(native,get(buy,"maxBatch()",["uint256"]))],"profit_convert")
    buffered=get(buy,"usd0Buffer()",["uint256"])
    if buffered:
        quote=p.get("quote") or p.get("wgooglx") or p["usd0"]
        if address(quote)!=address(p["usd0"]):
            from .hop import usd0_to_quote
            min_quote=max(buffered*10**12*99//100,1)
            if not cfg.get("localFixtureOnly"):return {"wait":"okx_hop_quote_required"}
            hop=bytes.fromhex(usd0_to_quote(min_quote)[2:])
            return action(chain,buy,"hopProfit(uint256,bytes)",["uint256","bytes"],[min_quote,hop],"profit_hop")
    pair=get(p["manager"],"pairOf(address)",["address"],["address"],[token])
    if int(pair,16) and get(buy,"escrowedTokens()",["uint256"]):return action(chain,buy,"flushEscrow()")
    budget=get(buy,"quoteBudget()",["uint256"])
    quote=p.get("quote") or p.get("wgooglx") or p["usd0"]
    min_buy=int(cfg.get("minimumBuybackQuoteWei") or cfg["minimumBuybackE6"]) if address(quote)!=address(p["usd0"]) else cfg["minimumBuybackE6"]
    max_buy=int(cfg.get("maxBuybackQuoteWei") or cfg["maxBuybackE6"]) if address(quote)!=address(p["usd0"]) else cfg["maxBuybackE6"]
    if budget<min_buy:return {"wait":"await_tax_or_realized_profit"}
    period=get(buy,"window()",["uint32"]);last=get(buy,"lastTimestamp()",["uint32"]);kind=get(buy,"oracleKind()",["uint8"])
    if kind!=(2 if int(pair,16) else 1) or last==0 or snap.timestamp-last>=period:return action(chain,buy,"observe()",kind="buyback_price_observe")
    if get(buy,"averageQ112()",["uint256"])==0:return {"wait":"buyback_price_warmup"}
    return action(chain,buy,"buyback(uint256)",["uint256"],[min(budget,max_buy)])
