import hashlib,json,re
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
from eth_abi import encode,decode
from eth_utils import keccak,to_checksum_address
ADDRESS=re.compile(r"^0x[0-9a-fA-F]{40}$")
def address(v):
    if not isinstance(v,str) or not ADDRESS.fullmatch(v):raise ValueError("Expected EVM address")
    return to_checksum_address(v)
def raw(v,length=None):
    if not isinstance(v,str) or not v.startswith("0x") or len(v)%2:raise ValueError("Expected hex bytes")
    try:b=bytes.fromhex(v[2:])
    except ValueError:raise ValueError("Expected hex bytes") from None
    if length is not None and len(b)!=length:raise ValueError("Wrong byte length")
    return b
def integer(v):
    if isinstance(v,bool):raise ValueError("Boolean is not an integer")
    x=int(v)
    if str(x)!=str(v) and not isinstance(v,int):raise ValueError("Noncanonical integer")
    return x
def units(v,decimals,rounding=ROUND_FLOOR):
    d=Decimal(str(v))
    if not d.is_finite():raise ValueError("Nonfinite quantity")
    return int((d*(10**decimals)).to_integral_value(rounding=rounding))
def calldata(signature,types,args):
    return "0x"+(keccak(text=signature)[:4]+encode(types,args)).hex()
def body_hash(types,args):return keccak(encode(types,args))
def object_hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()).hexdigest()
def decode_cctp(message):
    b=raw(message)
    if len(b)!=536:raise ValueError("Unexpected CCTP project message size")
    def n(p,length=32):return int.from_bytes(b[p:p+length],"big")
    def a(p):
        if any(b[p:p+12]):raise ValueError("Noncanonical EVM address word")
        return address("0x"+b[p+12:p+32].hex())
    if n(0,4)!=1 or n(148,4)!=1 or n(144,4)<2000:raise ValueError("Wrong CCTP version/finality")
    magic,kind,basis,sequence,evidence=decode(["bytes4","uint8","uint256","uint64","bytes32"],b[376:])
    if magic!=b"FT03" or kind>2 or sequence==0:raise ValueError("Wrong project hook")
    amount,fee,max_fee=n(216),n(312),n(280)
    if amount<=0 or fee>=amount or fee>max_fee:raise ValueError("Invalid CCTP amount/fee")
    return {"sourceDomain":n(4,4),"destinationDomain":n(8,4),"nonce":"0x"+b[12:44].hex(),"destinationCaller":a(108),
            "burnToken":a(152),"mintRecipient":a(184),"messageSender":a(248),"amount":amount,"fee":fee,
            "kind":kind,"basis":basis,"sequence":sequence,"evidence":"0x"+evidence.hex(),"messageHash":"0x"+keccak(b).hex()}
