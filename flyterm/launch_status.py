"""Read-only published-instance status. Public RPC only; no keys or writes."""
import json,urllib.request
from pathlib import Path
from eth_abi import encode,decode
from eth_utils import keccak,to_checksum_address
ROOT=Path(__file__).resolve().parents[1]
INSTANCE=ROOT/"config"/"ignix-instance.json"
def load_instance():
    return json.loads(INSTANCE.read_text(encoding="utf-8"))
def _rpc(url,method,params,timeout=8):
    req=urllib.request.Request(url,data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        out=json.loads(r.read())
    if "error" in out:raise RuntimeError(out["error"])
    return out["result"]
def _call(url,to,sig,types=(),args=(),outs=None):
    data="0x"+keccak(text=sig)[:4].hex()+(encode(types,args).hex() if types else "")
    res=_rpc(url,"eth_call",[{"to":to,"data":data},"latest"])
    if outs is None:return res
    if not res or res=="0x":return None
    values=decode(outs,bytes.fromhex(res[2:]))
    return values[0] if len(values)==1 else values
def live_status(rpc=None,instance=None):
    cfg=instance or load_instance()
    url=rpc or cfg.get("rpcPublic") or "https://rpc.xlayer.tech"
    token=to_checksum_address(cfg["token"]);manager=to_checksum_address(cfg["manager"])
    vault=to_checksum_address(cfg["vault"]);quote=to_checksum_address(cfg["quote"]);creator=to_checksum_address(cfg["creator"])
    types=["address","uint16","uint16","uint16","uint16","address","uint16","uint16","uint64","uint128","uint128","uint128","uint128","uint128","uint128","bytes32"]
    raw=_call(url,manager,"tokens(address)",["address"],[token])
    info=dict(zip(["creator","buyFeeBps","sellFeeBps","taxBuyBps","taxSellBps","quote","snipeStartBps","snipeMins","createdAt","vQuote","vToken","sold","collected","sellable","reserve","poolId"],decode(types,bytes.fromhex(raw[2:]))))
    dividend=_call(url,vault,"DIVIDEND_BPS()",outs=["uint16"])
    vault_creator=_call(url,vault,"CREATOR()",outs=["address"])
    vault_token=_call(url,vault,"TOKEN()",outs=["address"])
    vault_quote=_call(url,vault,"QUOTE()",outs=["address"])
    pair=_call(url,manager,"pairOf(address)",["address"],[token],["address"])
    accrued=_call(url,manager,"creatorAccrued(address,address)",["address","address"],[creator,quote],["uint256"])
    vault_bal=_call(url,quote,"balanceOf(address)",["address"],[vault],["uint256"])
    creator_bal=_call(url,quote,"balanceOf(address)",["address"],[creator],["uint256"])
    name=_call(url,token,"name()",outs=["string"]);symbol=_call(url,token,"symbol()",outs=["string"])
    checks={
        "templateMatchesFile":True,
        "creatorMatch":info["creator"].lower()==creator.lower() and str(vault_creator).lower()==creator.lower(),
        "quoteIsWgooglx":info["quote"].lower()==quote.lower() and str(vault_quote).lower()==quote.lower(),
        "taxBuy1pct":int(info["taxBuyBps"])==int(cfg["taxBuyBps"]),
        "taxSell1pct":int(info["taxSellBps"])==int(cfg["taxSellBps"]),
        "holderDividendZero":int(dividend)==int(cfg["dividendBps"])==0,
        "vaultTokenMatch":str(vault_token).lower()==token.lower(),
        "notGraduated":int(pair,16)==0,
    }
    return {
        "ok":all(checks.values()),
        "role":cfg["role"],
        "officialProduct":False,
        "chainId":cfg["chainId"],
        "token":token,"name":name,"symbol":symbol,
        "creator":to_checksum_address(info["creator"]),"vault":vault,"quote":to_checksum_address(info["quote"]),
        "templateId":cfg["templateId"],"taxBuyBps":int(info["taxBuyBps"]),"taxSellBps":int(info["taxSellBps"]),
        "dividendBps":int(dividend),"pair":pair,
        "vaultQuoteWei":str(vault_bal),"creatorQuoteWei":str(creator_bal),"creatorAccruedWei":str(accrued),
        "collectedQuoteWei":str(info["collected"]),"createTx":cfg["createTx"],"syncTx":cfg["syncTx"],"claimTx":cfg["claimTx"],
        "checks":checks,"notYetLive":cfg["notYetLive"],"hyperCanary":cfg["hyperCanary"],
        "links":{
            "token":cfg["explorerToken"]+token,
            "vault":cfg["explorerAddress"]+vault,
            "creator":cfg["explorerAddress"]+creator,
            "createTx":cfg["explorerTx"]+cfg["createTx"],
            "claimTx":cfg["explorerTx"]+cfg["claimTx"],
            "ignix":cfg["ignixApi"]+token,
        },
    }
def public_status():
    cfg=load_instance()
    if not cfg.get("published") or not cfg.get("token"):
        return {"ok":False,"live":False,"published":False,"officialProduct":False,"role":"unpublished"}
    try:
        live=live_status(instance=cfg);live["live"]=True;live["published"]=True;return live
    except Exception:
        return {"ok":False,"live":False,"published":True,"officialProduct":bool(cfg.get("officialProduct")),"error":"live_rpc_unavailable"}
