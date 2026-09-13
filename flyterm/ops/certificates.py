"""Exact EIP-712 and Solidity ABI payloads. Signing is separate from data collection."""
from eth_abi import encode
from eth_utils import keccak
from eth_account import Account
from eth_account.messages import encode_typed_data
from .codec import address,raw,calldata
COMMIT_FIELDS=[("runId","bytes32"),("modelHash","bytes32"),("nonce","uint64"),("fromRound","uint64"),("toRound","uint64"),("observedAt","uint64"),("deadline","uint64"),("referencePriceE8","uint64"),("previousRecord","bytes32"),("record","bytes32"),("previousState","bytes32"),("nextState","bytes32"),("inputHash","bytes32"),("side","uint8")]
SETTLEMENT_FIELDS=[("account","address"),("operation","bytes32"),("payload","bytes32"),("coreBlock","uint64"),("deadline","uint64"),("evidence","bytes32")]
ORDER_TYPE="(uint8,uint64,uint64,int256,uint64,uint64)"
COMMIT_TYPE="("+",".join(t for _,t in COMMIT_FIELDS[2:])+")"
def typed(kind,chain_id,contract,message):
    if kind not in ("Commit","Settlement"):raise ValueError("Unknown certificate")
    fields=COMMIT_FIELDS if kind=="Commit" else SETTLEMENT_FIELDS
    if set(message)!={x[0] for x in fields}:raise ValueError("Certificate fields differ")
    return {"types":{"EIP712Domain":[{"name":n,"type":t} for n,t in [("name","string"),("version","string"),("chainId","uint256"),("verifyingContract","address")]],kind:[{"name":n,"type":t} for n,t in fields]},
        "primaryType":kind,"domain":{"name":"FlyTerm Run Commit" if kind=="Commit" else "FlyTerm Venue Settlement","version":"1","chainId":int(chain_id),"verifyingContract":address(contract)},"message":message}
def sign(document,key,expected_signer):
    signer=Account.from_key(key)
    if signer.address.lower()!=address(expected_signer).lower():raise ValueError("Certificate signer mismatch")
    return "0x"+bytes(signer.sign_message(encode_typed_data(full_message=document)).signature).hex()
def recover(document,signature):
    return Account.recover_message(encode_typed_data(full_message=document),signature=signature)
def payload(label,types,values):
    return "0x"+keccak(encode(["string",*types],[label,*values])).hex()
def order_tuple(r):return tuple(r[k] for k in ("status","filledE8","averagePriceE8","closedPnlE6","feeE6","finalPositionE8"))
def settlement_call(action,values,core_block,deadline,evidence,signature):
    tail_types=["uint64","uint64","bytes32","bytes"];tail=[core_block,deadline,raw(evidence,32),raw(signature,65)]
    if action in ("settleDeposit","settleClassTransfer","settleExit"):types=["uint64","uint64"];args=[values["creditedE6"] if action!="settleExit" else values["netE6"],values["feeE6"]]
    elif action in ("settleSetup","rejectClassTransfer","rejectExit"):types=[];args=[]
    elif action=="settleOrder":types=[ORDER_TYPE];args=[order_tuple(values)]
    elif action=="bookCost":types=["bytes32","int256","bool"];args=[raw(values["id"],32),values["delta"],values["trading"]]
    else:raise ValueError("Unsupported settlement")
    all_types=types+tail_types
    return calldata(action+"("+",".join(all_types)+")",all_types,args+tail)
def commit_call(message,signature):
    values=[raw(message[n],32) if t=="bytes32" else message[n] for n,t in COMMIT_FIELDS[2:]]
    return calldata("submit("+COMMIT_TYPE+",bytes)",[COMMIT_TYPE,"bytes"],[tuple(values),raw(signature,65)])
