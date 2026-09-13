"""A bounded, read-only verifier. No configured production instance means no chain calls."""
import json,os,time,threading
from pathlib import Path
from eth_abi import encode,decode
from eth_utils import keccak,to_checksum_address
from .ops.rpc import Rpc
ROOT=Path(__file__).resolve().parents[1]
INSTANCE=ROOT/"config"/"ignix-instance.json"
_LOCK=threading.Lock();_CACHE={}

def load_instance():
    path=Path(os.environ.get("FLYTERM_INSTANCE_FILE") or INSTANCE)
    return json.loads(path.read_text(encoding="utf-8"))

def _rpc(url,method,params,timeout=8):
    # Reuse the project's bounded read transport; URL is never part of the response.
    return Rpc(url,196).call(method,params)

def live_status(rpc=None,instance=None):
    cfg=instance or load_instance();url=rpc or os.environ.get("FLYTERM_XLAYER_RPC") or cfg.get("rpcPublic")
    if not url:raise ValueError("Read RPC not configured")
    def at(k):return to_checksum_address(cfg[k])
    token,manager,vault,quote,creator,registry=[at(k) for k in ("token","manager","vault","quote","creator","registry")]
    chain=int(_rpc(url,"eth_chainId",[]),16)
    if chain!=int(cfg["chainId"]) or chain!=196:raise ValueError("Wrong chain")
    head=_rpc(url,"eth_getBlockByNumber",["latest",False]);tag=head["number"];stamp=int(head["timestamp"],16)
    if not -30<=int(time.time())-stamp<=90:raise ValueError("Stale chain")
    def call(to,sig,outs,types=(),args=()):
        data="0x"+keccak(text=sig)[:4].hex()+encode(types,args).hex()
        raw=_rpc(url,"eth_call",[{"to":to,"data":data},tag]);v=decode(outs,bytes.fromhex(raw[2:]))
        return v[0] if len(v)==1 else v
    types=["address","uint16","uint16","uint16","uint16","address","uint16","uint16","uint64","uint128","uint128","uint128","uint128","uint128","uint128","bytes32"]
    values=call(manager,"tokens(address)",types,["address"],[token])
    creator_on,buy_fee,sell_fee,tax_buy,tax_sell,quote_on=values[:6]
    related=call(manager,"vaultOf(address)",["address"],["address"],[token])
    factory=call(registry,"factoryOf(uint16)",["address"],["uint16"],[int(cfg["templateId"])])
    dividend=call(vault,"DIVIDEND_BPS()",["uint16"])
    vc=call(vault,"CREATOR()",["address"]);vt=call(vault,"TOKEN()",["address"]);vq=call(vault,"QUOTE()",["address"])
    pair=call(manager,"pairOf(address)",["address"],["address"],[token])
    owed=call(vault,"creatorOwed()",["uint256"])
    accrued=call(manager,"creatorAccrued(address,address)",["uint256"],["address","address"],[creator,quote])
    vb=call(quote,"balanceOf(address)",["uint256"],["address"],[vault])
    cb=call(quote,"balanceOf(address)",["uint256"],["address"],[creator])
    receipt=_rpc(url,"eth_getTransactionReceipt",[cfg["createTx"]]);event_ok=False;receipt_ok=False
    if receipt and receipt.get("status")=="0x1":
        block=_rpc(url,"eth_getBlockByNumber",[receipt["blockNumber"],False])
        receipt_ok=bool(block and block["hash"]==receipt["blockHash"] and int(tag,16)-int(receipt["blockNumber"],16)+1>=int(cfg.get("confirmations",12)))
        topic="0x"+keccak(text="TokenCreated(address,address,address,uint256,string,address,address,uint16)").hex()
        matches=[]
        for log in receipt.get("logs",[]):
            if log["address"].lower()!=manager.lower() or len(log.get("topics",[]))!=4 or log["topics"][0].lower()!=topic:continue
            identities=["0x"+x[-40:] for x in log["topics"][1:]]
            if [x.lower() for x in identities]!=[x.lower() for x in (token,creator,quote)]:continue
            _,_,event_vault,_,template=decode(["uint256","string","address","address","uint16"],bytes.fromhex(log["data"][2:]))
            matches.append(event_vault.lower()==vault.lower() and int(template)==int(cfg["templateId"]))
        event_ok=len(matches)==1 and matches[0]
    checks={"chainMatches":True,"freshBlock":True,"creationConfirmed":receipt_ok,"templateCreationEvent":event_ok,
            "registryFactoryMatches":factory.lower()==at("expectedFactory").lower(),"managerVaultMatches":related.lower()==vault.lower(),
            "creatorMatch":creator_on.lower()==creator.lower()==vc.lower(),"quoteMatch":quote_on.lower()==quote.lower()==vq.lower(),
            "vaultTokenMatch":vt.lower()==token.lower(),"taxBuyMatches":int(tax_buy)==int(cfg["taxBuyBps"]),
            "taxSellMatches":int(tax_sell)==int(cfg["taxSellBps"]),"holderDividendZero":int(dividend)==int(cfg["dividendBps"])==0}
    return {"schema":"fly-verification/v1","ok":all(checks.values()),"published":True,"live":True,"role":cfg["role"],
            "officialProduct":bool(cfg.get("officialProduct")) and cfg["role"]=="production","chainId":chain,"blockNumber":int(tag,16),"blockHash":head["hash"],"observedAt":stamp*1000,
            "token":token,"creator":creator,"vault":vault,"quote":quote,"registry":registry,"factory":factory,"templateId":int(cfg["templateId"]),
            "taxBuyBps":int(tax_buy),"taxSellBps":int(tax_sell),"dividendBps":int(dividend),"pair":pair,"graduated":int(pair,16)!=0,
            "vaultQuoteWei":str(vb),"creatorQuoteWei":str(cb),"creatorTaxOwedWei":str(owed),"managerCreatorFeesWei":str(accrued),
            "createTx":cfg["createTx"],"checks":checks,"scope":"launch identity and tax configuration; not neural computation or profitability proof"}

def public_status():
    try:cfg=load_instance()
    except Exception:return {"schema":"fly-verification/v1","ok":False,"live":False,"published":False,"error":"instance_config_unavailable"}
    if not cfg.get("published") or not cfg.get("token"):
        return {"schema":"fly-verification/v1","ok":False,"live":False,"published":False,"officialProduct":False,"role":"unpublished","checks":{}}
    key=json.dumps(cfg,sort_keys=True)
    with _LOCK:
        if _CACHE.get("key")==key and time.monotonic()-_CACHE.get("at",0)<15:return _CACHE["value"]
        try:out=live_status(instance=cfg)
        except Exception:out={"schema":"fly-verification/v1","ok":False,"live":False,"published":True,"officialProduct":bool(cfg.get("officialProduct")),"role":cfg.get("role"),"error":"verification_unavailable","checks":{}}
        _CACHE.update(key=key,at=time.monotonic(),value=out)
        return out
