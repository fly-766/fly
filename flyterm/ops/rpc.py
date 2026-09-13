"""Bounded backend-only RPC. Credentials and authenticated URLs are never logged."""
import json,urllib.request
from .codec import calldata
class RpcError(RuntimeError):pass
class Rpc:
    def __init__(self,url,chain_id):
        if not url:raise RpcError("RPC URL is not configured")
        self._url=url;self.chain_id=int(chain_id)
    def _request(self,payload):
        req=urllib.request.Request(self._url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","User-Agent":"FlyTerm/0.3"})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:data=json.loads(r.read(4_000_000))
        except Exception:raise RpcError("RPC transport unavailable") from None
        return data
    def call(self,method,params):
        data=self._request({"jsonrpc":"2.0","id":1,"method":method,"params":params})
        if not isinstance(data,dict) or data.get("id")!=1:raise RpcError("RPC response identity mismatch")
        if "error" in data:raise RpcError("RPC method failed: "+method+" code="+str(data["error"].get("code"))) from None
        if "result" not in data:raise RpcError("RPC result missing")
        return data["result"]
    def batch(self,calls):
        readonly={"eth_call","eth_getBalance","eth_getCode","eth_getStorageAt","eth_getTransactionReceipt","eth_getTransactionCount","eth_getBlockByNumber","eth_chainId","eth_blockNumber","eth_gasPrice"}
        if not 1<=len(calls)<=100 or any(method not in readonly for method,params in calls):raise RpcError("Invalid read-only RPC batch")
        data=self._request([{"jsonrpc":"2.0","id":i+1,"method":method,"params":params} for i,(method,params) in enumerate(calls)])
        if not isinstance(data,list) or len(data)!=len(calls):raise RpcError("Incomplete RPC batch")
        rows={row.get("id"):row for row in data}
        if set(rows)!=set(range(1,len(calls)+1)):raise RpcError("RPC batch identity mismatch")
        if any("error" in row or "result" not in row for row in rows.values()):raise RpcError("RPC batch call failed")
        return [rows[i+1]["result"] for i in range(len(calls))]
    def verify_chain(self):
        actual=int(self.call("eth_chainId",[]),16)
        if actual!=self.chain_id:raise RpcError("RPC chain mismatch")
        return actual
    def view(self,to,signature,types=(),args=(),block="latest"):
        return self.call("eth_call",[{"to":to,"data":calldata(signature,list(types),list(args))},block])
    def receipt(self,tx_hash):return self.call("eth_getTransactionReceipt",[tx_hash])
    def code(self,at):return self.call("eth_getCode",[at,"latest"])
