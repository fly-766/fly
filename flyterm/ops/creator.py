"""Creator-wallet claim for System Vault (template 0). 1% tax arrives as wGOOGLx and is swept to the converter."""
from eth_utils import keccak
from .codec import address,raw,calldata,object_hash
TRANSFER="0x"+keccak(text="Transfer(address,address,uint256)").hex()
def sweep_plan(receipt,transaction,config):
    creator=address(config["signerAddress"]);manager=address(config["creatorIncome"]["manager"]);quote=address(config["creatorIncome"]["quote"]);to=address(config["creatorIncome"]["converter"])
    vault=config["creatorIncome"].get("vault")
    claim_to=address(vault) if vault else manager
    expected=calldata("claimCreator()",[],[]) if vault else calldata("claimCreatorFees(address)",["address"],[quote])
    if receipt["status"]!="0x1" or transaction["from"].lower()!=creator.lower() or transaction["to"].lower()!=claim_to.lower() or transaction["input"].lower()!=expected.lower():raise ValueError("Not this creator's fixed claim")
    delta=0
    for log in receipt["logs"]:
        if log["address"].lower()!=quote.lower() or len(log["topics"])!=3 or log["topics"][0].lower()!=TRANSFER:continue
        sender=address("0x"+log["topics"][1][-40:]);recipient=address("0x"+log["topics"][2][-40:]);amount=int(log["data"],16)
        if recipient==creator and (not vault or sender==claim_to):delta+=amount
        if sender==creator:delta-=amount
    if delta<=0 or delta>int(config["creatorIncome"].get("maxSweepWei") or config["creatorIncome"]["maxSweepE6"]):raise ValueError("Creator claim amount outside approved sweep")
    return {"chainId":config["chainId"],"to":quote,"value":"0","data":calldata("transfer(address,uint256)",["address","uint256"],[to,delta]),
            "creatorClaimTx":receipt["transactionHash"],"creatorClaimBlockHash":receipt["blockHash"]}
def validate_sweep(intent,rpc,config):
    receipt=rpc.receipt(intent["creatorClaimTx"]);tx=rpc.call("eth_getTransactionByHash",[intent["creatorClaimTx"]])
    if not receipt or not tx:raise ValueError("Creator claim unavailable")
    block=rpc.call("eth_getBlockByNumber",[receipt["blockNumber"],False]);head=int(rpc.call("eth_blockNumber",[]),16)
    if block["hash"]!=receipt["blockHash"] or head-int(receipt["blockNumber"],16)+1<config["confirmations"]:raise ValueError("Creator claim not final")
    if intent!=sweep_plan(receipt,tx,config):raise ValueError("Creator sweep changed")


def creator_step(snapshot,config,journal):
    """System Vault income, distinct from Manager LP/platform creator fees."""
    import json
    c=config.get("creatorIncome")
    if not c or not c.get("vault"):return None
    creator=address(config["signerAddress"]);vault=address(c["vault"]);quote=address(c["quote"])
    get=snapshot.get
    if address(get(c["manager"],"vaultOf(address)",["address"],["address"],[config["projectToken"]]))!=vault:raise ValueError("Tax vault binding changed")
    for sig,expected in (("CREATOR()",creator),("QUOTE()",quote),("TOKEN()",address(config["projectToken"]))):
        if address(get(vault,sig,["address"]))!=expected:raise ValueError("Tax vault identity changed")
    if get(vault,"DIVIDEND_BPS()",["uint16"])!=0:raise ValueError("Unexpected holder distribution")
    # Finish each proven receipt before claiming again. A receipt is consumed once.
    rows=journal.db.execute("SELECT receipt FROM ops WHERE chain=? AND signer=? AND kind='creator_tax_claim' AND state='CONFIRMED' ORDER BY created,rowid",(config["chainId"],creator.lower())).fetchall()
    assigned={json.loads(r[0]).get("creatorClaimTx"):r for r in journal.db.execute("SELECT intent,state FROM ops WHERE chain=? AND signer=?",(config["chainId"],creator.lower()))}
    for row in rows:
        receipt=json.loads(row[0]);txhash=receipt["transactionHash"]
        if txhash in assigned:
            saved=assigned[txhash]
            if saved[1]=="CONFIRMED":continue
            if saved[1]=="PLANNED":return {"kind":"creator_tax_sweep","intent":json.loads(saved[0])}
            raise ValueError("Prior tax sweep needs reconciliation")
        tx=snapshot.rpc.call("eth_getTransactionByHash",[txhash])
        intent=sweep_plan(receipt,tx,config)
        return {"kind":"creator_tax_sweep","intent":intent}
    if get(config["addresses"]["converter"],"paused()",["bool"]):return None
    owed=int(get(vault,"creatorOwed()",["uint256"]));balance=int(get(quote,"balanceOf(address)",["uint256"],["address"],[vault]))
    minimum=int(c["minimumClaimWei"]);maximum=int(c["maxSweepWei"])
    if owed>maximum or balance>maximum:raise ValueError("Tax claim exceeds reviewed sweep budget")
    def plan(sig,kind):return {"kind":kind,"intent":{"chainId":config["chainId"],"to":vault,"value":"0","data":calldata(sig,[],[])}}
    if owed>=minimum:return plan("claimCreator()","creator_tax_claim")
    if balance>=minimum and balance>owed:return plan("sync()","creator_tax_sync")
    return None
