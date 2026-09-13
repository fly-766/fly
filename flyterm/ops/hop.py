"""Unsigned OKX quotes; the fixed contract enforces exact input and minimum output."""
import json,os,subprocess,time
from decimal import Decimal,InvalidOperation
from .codec import calldata,address,raw,object_hash

class QuoteUnavailable(ValueError): pass

def quote_to_usd0(min_usd0):
    return calldata("hopQuoteToUsd0(uint256)",["uint256"],[int(min_usd0)])
def usd0_to_quote(min_quote):
    return calldata("hopUsd0ToQuote(uint256)",["uint256"],[int(min_quote)])
def uses_googl_quote(protocol):
    return address(protocol.get("quote") or protocol.get("wgooglx") or protocol["usd0"])!=address(protocol["usd0"])

def validate_quote(document,request,policy,now=None):
    now=int(time.time()) if now is None else int(now)
    try:
        issued=int(document["quotedAt"])
        if not 0<=now-issued<=int(policy["maxAgeSeconds"]):raise ValueError("Expired quote")
        row=document["response"]["data"]
        if len(row)!=1:raise ValueError("Ambiguous quote")
        row=row[0];route=row["routerResult"];tx=row["tx"]
        if route.get("action")!="ok" or route.get("swapMode")!="exactIn":raise ValueError("Route not accepted")
        if int(route["chainIndex"])!=int(request["chainId"]):raise ValueError("Quote chain mismatch")
        for side,key in (("fromToken","source"),("toToken","destination")):
            if address(route[side]["tokenContractAddress"])!=address(request[key]):raise ValueError("Quote asset mismatch")
        if int(route["fromTokenAmount"])!=int(request["amount"]) or int(request["amount"])<=0:raise ValueError("Quote amount mismatch")
        if address(tx["from"])!=address(request["receiver"]) or address(tx["to"])!=address(policy["router"]):raise ValueError("Quote destination mismatch")
        if int(tx.get("value","0"))!=0:raise ValueError("Native value not allowed")
        data=raw(tx["data"])
        if len(data)<4 or len(data)>100000 or "0x"+data[:4].hex() not in policy["selectors"]:raise ValueError("Unreviewed router method")
        amount=int(route["toTokenAmount"]);minimum=int(tx["minReceiveAmount"])
        slip=int(policy["maxSlippageBps"])
        impact=Decimal(str(route["priceImpactPercent"]));quoted_slip=Decimal(str(tx["slippagePercent"]))
        if not impact.is_finite() or not quoted_slip.is_finite() or abs(impact)*100>int(policy["maxPriceImpactBps"]):raise ValueError("Price impact exceeds cap")
        if quoted_slip<0 or quoted_slip*100>slip or not 0<minimum<=amount or minimum<amount*(10000-slip)//10000:raise ValueError("Minimum output below policy")
        return {"data":"0x"+data.hex(),"minimum":minimum,"quoteHash":object_hash(document),"quotedAt":issued,
                "expiresAt":issued+int(policy["maxAgeSeconds"]),"source":address(request["source"]),"destination":address(request["destination"]),
                "receiver":address(request["receiver"]),"amount":str(request["amount"]),"expected":str(amount)}
    except (KeyError,TypeError,ValueError,InvalidOperation,OverflowError) as error:
        raise QuoteUnavailable("Unsigned quote failed policy checks") from error

class OkxQuotes:
    def __init__(self,run=None,clock=time.time):
        self.run=run or subprocess.run;self.clock=clock
    def quote(self,source,destination,amount,receiver,cfg):
        policy=cfg["okxQuotes"]
        if not policy.get("enabled"):raise QuoteUnavailable("Quote service is not configured")
        if address(policy["router"])!=address(cfg["protocol"]["hopRouter"]) or address(policy["spender"])!=address(cfg["protocol"]["hopSpender"]):raise QuoteUnavailable("Router policy mismatch")
        issued=int(self.clock())
        request={"source":source,"destination":destination,"amount":str(amount),"receiver":receiver,"chainId":cfg["chainId"]}
        command=[os.environ.get("FLYTERM_OKX_CLI","onchainos"),"swap","swap","--from",address(source),"--to",address(destination),
                 "--amount",str(amount),"--chain",str(cfg["chainId"]),"--wallet",address(receiver),"--max-auto-slippage",str(Decimal(policy["maxSlippageBps"])/100)]
        try:
            result=self.run(command,capture_output=True,text=True,timeout=20,check=False)
            if result.returncode!=0 or len(result.stdout)>1000000:raise QuoteUnavailable("Quote transport unavailable")
            response=json.loads(result.stdout)
            if response.get("ok") is not True:raise QuoteUnavailable("Quote transport unavailable")
            return validate_quote({"quotedAt":issued,"response":response},request,policy,int(self.clock()))
        except (OSError,subprocess.SubprocessError,json.JSONDecodeError) as error:
            raise QuoteUnavailable("Quote transport unavailable") from error

def validate_intent_quote(intent,config):
    """Recheck freshness and calldata binding immediately before signing/replacement."""
    from eth_abi import decode
    q=intent["hopQuote"];data=raw(intent["data"]);to=address(intent["to"]);a=config["addresses"];p=config["protocol"]
    if not int(q["quotedAt"])<=int(time.time())<=int(q["expiresAt"]):raise QuoteUnavailable("Quote expired before signing")
    if int(q["expiresAt"])-int(q["quotedAt"])>int(config["okxQuotes"]["maxAgeSeconds"]):raise QuoteUnavailable("Quote age changed")
    if to==address(a["converter"]) and data[:4]==raw(calldata("convert(uint256,uint256,bytes)",[],[])[:10]):
        amount,minimum,hop=decode(["uint256","uint256","bytes"],data[4:]);source=p.get("quote") or p["wgooglx"];dest=p["usd0"]
        if amount!=int(q["amount"]):raise QuoteUnavailable("Quote amount changed")
    elif to==address(a["buyback"]) and data[:4]==raw(calldata("hopProfit(uint256,bytes)",[],[])[:10]):
        minimum,hop=decode(["uint256","bytes"],data[4:]);source=p["usd0"];dest=p.get("quote") or p["wgooglx"]
    else:raise QuoteUnavailable("Quote attached to wrong operation")
    if minimum!=int(q["minimum"]) or hop!=raw(q["data"]) or to!=address(q["receiver"]) or address(source)!=address(q["source"]) or address(dest)!=address(q["destination"]):raise QuoteUnavailable("Quote binding changed")
