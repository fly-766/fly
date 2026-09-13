"""No key access in plan mode. Every signed operation is bound to the exact approved config."""
import json,os
from pathlib import Path
from eth_account import Account
from eth_utils import keccak
from .codec import object_hash,address,raw
class NotArmed(RuntimeError):pass
class Executor:
    def __init__(self,config,journal,rpc,key_loader=None):
        self.config=config;self.journal=journal;self.rpc=rpc;self._verified_pins_for=None;self.key_loader=key_loader or self._key
    def _key(self):
        p=os.environ.get(self.config["signerKeyFileEnv"])
        if not p:raise NotArmed("Signer key file is not configured")
        try:return Path(p).read_text().strip()
        except Exception:raise NotArmed("Signing material unavailable") from None
    def _armed(self,approved):
        if not self.config.get("liveEnabled") or approved!=object_hash(self.config):raise NotArmed("Exact live config approval required")
        self.rpc.verify_chain();self.verify_code_pins()
    def verify_code_pins(self):
        if not self.config.get("requireCodePins"):return
        config_hash=object_hash(self.config)
        if self._verified_pins_for==config_hash:return
        pins={address(a).lower():v for a,v in self.config.get("runtimeCodeHashes",{}).items()}
        required=set(self.config.get("allowedCalls",{}))|{address(a).lower() for a in self.config.get("requiredReadCodePins",[])}
        if not pins or not required<=set(pins):raise NotArmed("Deployed runtime code fingerprints required")
        values=self.rpc.batch([("eth_getCode",[a,"latest"]) for a in pins])
        for (at,expected),value in zip(pins.items(),values):
            code=raw(value)
            if not code or "0x"+keccak(code).hex()!=expected.lower():raise NotArmed("Deployed runtime changed")
        self._verified_pins_for=config_hash
    def validate(self,intent):
        if intent.get("chainId")!=self.config["chainId"]:raise ValueError("Intent chain mismatch")
        data=raw(intent["data"]);value=int(intent.get("value","0"))
        if "operationContext" in intent:raw(intent["operationContext"],32)
        if value<0 or value>int(self.config["maxCallValueWei"]):raise ValueError("Value budget exceeded")
        if intent.get("to") is None:
            if "0x"+keccak(data).hex() not in self.config.get("allowedDeployments",[]):raise ValueError("Creation code not allowlisted")
            if "expectedNonce" not in intent:raise ValueError("Deployment nonce required")
            to=None
        else:
            to=address(intent["to"]);allowed=self.config["allowedCalls"].get(to.lower(),[])
            if len(data)<4 or "0x"+data[:4].hex() not in allowed:raise ValueError("Call not allowlisted")
            pinned=self.config.get("exactCalls",{}).get(to.lower(),{})
            selector="0x"+data[:4].hex()
            if selector in pinned and "0x"+keccak(data).hex() not in pinned[selector]:raise ValueError("Calldata differs from approved launch")
            if self.config.get("creatorIncome") and to.lower()==self.config["creatorIncome"]["quote"].lower() and selector=="0xa9059cbb" and "creatorClaimTx" not in intent:raise ValueError("Creator sweep requires its own claim receipt")
        if self.config.get("okxQuotes") and to and data[:4].hex() in (""+keccak(text="convert(uint256,uint256,bytes)")[:4].hex(),keccak(text="hopProfit(uint256,bytes)")[:4].hex()):
            if "hopQuote" not in intent:raise NotArmed("Fresh unsigned quote required")
            from .hop import validate_intent_quote
            validate_intent_quote(intent,self.config)
        return to,data,value
    def reconcile(self,id):
        row=self.journal.get(id)
        if not row:raise ValueError("Unknown operation")
        self._same_config(row)
        for a in self.journal.attempts(id):
            receipt=self.rpc.receipt(a["hash"])
            if not receipt:continue
            block=self.rpc.call("eth_getBlockByNumber",[receipt["blockNumber"],False])
            if not block or block["hash"].lower()!=receipt["blockHash"].lower():continue
            head=int(self.rpc.call("eth_blockNumber",[]),16)
            confirmations=head-int(receipt["blockNumber"],16)+1
            done=confirmations>=int(self.config.get("confirmations",3))
            self.journal.mined(id,receipt,done)
            return {"id":id,"state":self.journal.get(id)["state"],"txHash":receipt["transactionHash"],"confirmations":confirmations}
        self.journal.state(id,"UNKNOWN")
        return {"id":id,"state":"UNKNOWN"}
    def _same_config(self,row):
        if row["config"]!=object_hash(self.config) or row["chain"]!=self.config["chainId"] or row["signer"]!=self.config["signerAddress"].lower():
            raise NotArmed("Operation belongs to another approved configuration")
    def _preflight(self,intent):
        to,data,value=self.validate(intent);sender=address(self.config["signerAddress"])
        if "creatorClaimTx" in intent:
            from .creator import validate_sweep
            validate_sweep(intent,self.rpc,self.config)
        tx={"from":sender,"data":"0x"+data.hex(),"value":hex(value)}
        if to:tx["to"]=to
        self.rpc.call("eth_call",[tx,"latest"])
        gas=int(self.rpc.call("eth_estimateGas",[tx]),16)*120//100
        return tx,gas
    def _sign(self,id,intent,nonce,gas,price):
        if gas>int(self.config["maxGasUnits"]) or price>int(self.config["maxGasPriceWei"]):raise NotArmed("Gas budget exceeded")
        reserved=self.journal.daily_gas(self.config["chainId"],self.config["signerAddress"],exclude=id)
        if reserved+gas*price+int(intent.get("value","0"))>int(self.config["maxDailyGasWei"]):raise NotArmed("Daily gas budget exceeded")
        to,data,value=self.validate(intent)
        try:signer=Account.from_key(self.key_loader())
        except Exception:raise NotArmed("Signing material invalid") from None
        if signer.address.lower()!=self.config["signerAddress"].lower():raise NotArmed("Signer address mismatch")
        tx={"chainId":self.config["chainId"],"nonce":nonce,"data":data,"value":value,"gas":gas,"gasPrice":price}
        if to:tx["to"]=to
        signed=signer.sign_transaction(tx);raw_tx="0x"+bytes(signed.raw_transaction).hex();txhash="0x"+keccak(signed.raw_transaction).hex()
        self.journal.signed(id,nonce,raw_tx,txhash,gas,price);return raw_tx,txhash
    def _send(self,id,raw_tx,txhash):
        try:
            returned=self.rpc.call("eth_sendRawTransaction",[raw_tx])
            if returned.lower()!=txhash.lower():raise ValueError("Hash mismatch")
            self.journal.state(id,"SUBMITTED")
        except Exception:self.journal.state(id,"UNKNOWN")
        return {"id":id,"state":self.journal.get(id)["state"],"txHash":txhash}
    def submit(self,kind,intent,*,live=False,approved_hash=None):
        self.validate(intent)
        row=self.journal.plan(self.config["chainId"],self.config["signerAddress"],object_hash(self.config),kind,intent)
        if not live:return {"id":row["id"],"state":row["state"],"signingEnabled":False,"broadcastEnabled":False}
        self._armed(approved_hash)
        if row["state"] in ("CONFIRMED","REVERTED"):return {"id":row["id"],"state":row["state"]}
        if row["state"]!="PLANNED":return self.reconcile(row["id"])
        if self.journal.pending(self.config["chainId"],self.config["signerAddress"]):raise NotArmed("Earlier transaction unresolved")
        _,gas=self._preflight(intent)
        nonce=int(self.rpc.call("eth_getTransactionCount",[self.config["signerAddress"],"pending"]),16)
        if "expectedNonce" in intent and nonce!=int(intent["expectedNonce"]):raise NotArmed("Deployment nonce changed")
        price=int(self.rpc.call("eth_gasPrice",[]),16)
        raw_tx,txhash=self._sign(row["id"],intent,nonce,gas,price)
        return self._send(row["id"],raw_tx,txhash)
    def resume(self,id,*,approved_hash,replace=False):
        self._armed(approved_hash);row=self.journal.get(id)
        if not row:raise ValueError("Unknown operation")
        self._same_config(row)
        result=self.reconcile(id)
        if result["state"] in ("CONFIRMED","REVERTED","MINED"):return result
        attempts=self.journal.attempts(id)
        if not attempts:raise ValueError("No signed transaction")
        latest=attempts[-1]
        if not replace:return self._send(id,latest["raw"],latest["hash"])
        if len(attempts)>=3:raise NotArmed("Replacement limit reached")
        intent=json.loads(row["intent"]);_,gas=self._preflight(intent)
        # Same recipient, calldata, value and nonce; only gas changes within the approved ceiling.
        price=max((latest["price"]*125+99)//100,int(self.rpc.call("eth_gasPrice",[]),16))
        raw_tx,txhash=self._sign(id,intent,row["nonce"],gas,price)
        return self._send(id,raw_tx,txhash)
