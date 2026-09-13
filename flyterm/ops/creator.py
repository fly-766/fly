"""Creator-wallet claim for System Vault (template 0). 1% tax arrives as wGOOGLx and is swept to the converter."""
from eth_utils import keccak
from .codec import address,raw,calldata,object_hash
TRANSFER="0x"+keccak(text="Transfer(address,address,uint256)").hex()
def sweep_plan(receipt,transaction,config):
    creator=address(config["signerAddress"]);manager=address(config["creatorIncome"]["manager"]);quote=address(config["creatorIncome"]["quote"]);to=address(config["creatorIncome"]["converter"])
    expected=calldata("claimCreatorFees(address)",["address"],[quote])
    if receipt["status"]!="0x1" or transaction["from"].lower()!=creator.lower() or transaction["to"].lower()!=manager.lower() or transaction["input"].lower()!=expected.lower():raise ValueError("Not this creator's fixed claim")
    delta=0
    for log in receipt["logs"]:
        if log["address"].lower()!=quote.lower() or len(log["topics"])!=3 or log["topics"][0].lower()!=TRANSFER:continue
        sender=address("0x"+log["topics"][1][-40:]);recipient=address("0x"+log["topics"][2][-40:]);amount=int(log["data"],16)
        if recipient==creator:delta+=amount
        if sender==creator:delta-=amount
    if delta<=0 or delta>int(config["creatorIncome"]["maxSweepE6"]):raise ValueError("Creator claim amount outside approved sweep")
    return {"chainId":config["chainId"],"to":quote,"value":"0","data":calldata("transfer(address,uint256)",["address","uint256"],[to,delta]),
            "creatorClaimTx":receipt["transactionHash"],"creatorClaimBlockHash":receipt["blockHash"]}
def validate_sweep(intent,rpc,config):
    receipt=rpc.receipt(intent["creatorClaimTx"]);tx=rpc.call("eth_getTransactionByHash",[intent["creatorClaimTx"]])
    if not receipt or not tx:raise ValueError("Creator claim unavailable")
    block=rpc.call("eth_getBlockByNumber",[receipt["blockNumber"],False]);head=int(rpc.call("eth_blockNumber",[]),16)
    if block["hash"]!=receipt["blockHash"] or head-int(receipt["blockNumber"],16)+1<config["confirmations"]:raise ValueError("Creator claim not final")
    if intent!=sweep_plan(receipt,tx,config):raise ValueError("Creator sweep changed")
