"""Prepare and validate an IGNIX System Vault (template 0) launch. No upload, authentication or network writes."""
from eth_abi import encode
from .codec import address,raw,calldata
PARAMS=[("name","string"),("symbol","string"),("metadataURI","string"),("salt","bytes32"),("quote","address"),("graduation","uint256"),("buyFeeBps","uint16"),("sellFeeBps","uint16"),("taxBuyBps","uint16"),("taxSellBps","uint16"),("snipeStartBps","uint16"),("snipeMins","uint16"),("listingFee","uint256"),("firstBuy","uint256"),("founderBps","uint16"),("founderSecs","uint32"),("founderRoot","bytes32")]
PARAM_TYPE="("+",".join(t for _,t in PARAMS)+")"
ZERO="0x"+"00"*32
WGOOGLX="0xf8c5308F80E459bb53d9EbE689854d9cBb2Caa6f"
SYSTEM_FACTORY="0xb47856525d014eb27335c4fcd25f91ad1be6c006"
def vault_data(holder_bps=0):
    if not 0<=int(holder_bps)<=10000:raise ValueError("Holder dividend bps out of range")
    return "0x"+encode(["uint256","uint256","uint256","uint256","uint256"],[int(holder_bps),0,0,0,0]).hex()
def inspect_system_vault(data):
    raw_bytes=raw(data)
    if len(raw_bytes)!=160:raise ValueError("IGNIX System Vault data layout changed; expected five ABI words")
    holder=int.from_bytes(raw_bytes[:32],"big")
    if holder>10000:raise ValueError("IGNIX System Vault dividendBps invalid")
    return {"dividendBps":holder}
def request(draft,creator,quote=None):
    if draft.get("taxBuyBps") is None or draft.get("taxSellBps") is None:raise ValueError("Tax rates still need the user's launch choice")
    if int(draft["taxBuyBps"])!=100 or int(draft["taxSellBps"])!=100:raise ValueError("This route is fixed at 1% buy and 1% sell tax")
    q=address(quote or draft.get("quote") or WGOOGLX)
    if q!=address(WGOOGLX):raise ValueError("Quote token must be wGOOGLx")
    return {"creator":address(creator),"name":draft["name"],"symbol":draft["symbol"],"metadataURI":draft.get("metadataURI") or "","quote":q,
        "taxEnabled":True,"taxBuyBps":100,"taxSellBps":100,"dividendBps":0,"creatorBps":10000,
        "snipeStartBps":0,"snipeMins":0,"firstBuy":str(draft["firstBuy"]) if draft.get("firstBuy") is not None else None,
        "templateId":0,"graduationProtectionDays":draft.get("graduationProtectionDays",7),
        "webpageLaunch":True,"taxRecipients":[]}
def validate_response(response,expected,limits,manager,chain_id=196):
    v=response["data"] if "data" in response else response;p=v["params"]
    for k in ("name","symbol","quote","taxBuyBps","taxSellBps"):
        if str(p[k]).lower()!=str(expected[k]).lower():raise ValueError("IGNIX returned different launch field: "+k)
    if expected.get("metadataURI") not in (None,"") and str(p.get("metadataURI","")).lower()!=str(expected["metadataURI"]).lower():
        raise ValueError("IGNIX returned different launch field: metadataURI")
    if int(v["templateId"])!=0:raise ValueError("Tax recipient or template mismatch")
    vault=inspect_system_vault(v["vaultData"])
    if vault["dividendBps"]!=0:raise ValueError("Holder dividend must be 0 so 1% tax stays with the creator")
    if int(p["founderBps"])!=0 or int(p["founderSecs"])!=0 or p["founderRoot"].lower()!=ZERO:raise ValueError("Unexpected founder allocation")
    if address(v["factory"])!=address(limits.get("factory") or SYSTEM_FACTORY) or int(v["venue"])!=int(limits["venue"]):raise ValueError("Factory/venue mismatch")
    if int(p["listingFee"])>int(limits["maxListingFeeRaw"]) or int(p["graduation"])!=int(limits["graduationRaw"]):raise ValueError("Launch cost/target mismatch")
    if int(v["graduationProtectionSecs"])!=int(expected.get("graduationProtectionDays",7))*86400:raise ValueError("Protection period mismatch")
    if int(p["buyFeeBps"])>limits["maxPlatformFeeBps"] or int(p["sellFeeBps"])>limits["maxPlatformFeeBps"]:raise ValueError("Platform fee cap exceeded")
    if address(p["quote"])!=address(WGOOGLX):raise ValueError("Quote token must be wGOOGLx")
    if int(p["taxBuyBps"])!=100 or int(p["taxSellBps"])!=100:raise ValueError("Tax must be 1% / 1%")
    if address(v["tokenAddress"])!=address(limits["expectedToken"]):raise ValueError("Token prediction mismatch")
    first=expected.get("firstBuy")
    if first is not None and str(p["firstBuy"])!=str(first):raise ValueError("IGNIX returned different launch field: firstBuy")
    vals=[raw(p[n],32) if t=="bytes32" else p[n] if t in ("string","address") else int(p[n]) for n,t in PARAMS]
    types=[PARAM_TYPE,"uint16","bytes","uint64","address","uint8","uint64","bytes"]
    args=[tuple(vals),0,raw(v["vaultData"]),int(v["deadline"]),address(v["factory"]),int(v["venue"]),int(v["graduationProtectionSecs"]),raw(v["signature"])]
    intent={"chainId":chain_id,"to":address(manager),"value":"0","data":calldata("createToken("+",".join(types)+")",types,args)}
    spend=str(int(p["listingFee"])+int(p["firstBuy"]))
    return {"intent":intent,"quoteApprovalRaw":spend,"quoteApprovalE6":spend,"tokenAddress":address(v["tokenAddress"]),"signatureDeadline":int(v["deadline"]),"signingEnabled":False,"broadcastEnabled":False,"webpageLaunchPreferred":True}
