"""A consistent EVM block snapshot; native precompiles are read through the deployed reader."""
from eth_abi import decode
from .codec import raw,address,calldata
STATE_TYPE="(int64,uint64,uint64,int64,int64,uint64,uint8,bool,bool)"
class Snapshot:
    def __init__(self,rpc,confirmations=1):
        self.rpc=rpc;self.account_cache={}
        self.block=rpc.call("eth_getBlockByNumber",["latest",False])
        if confirmations>1:
            number=max(0,int(self.block["number"],16)-int(confirmations)+1)
            self.block=rpc.call("eth_getBlockByNumber",[hex(number),False])
        self.tag=self.block["number"]
        self.timestamp=int(self.block["timestamp"],16)
    def get(self,at,signature,outputs,types=(),args=()):
        value=self.rpc.view(address(at),signature,types,args,self.tag)
        out=decode(outputs,raw(value))
        return out[0] if len(out)==1 else out
    def core(self,reader,user):
        values=self.get(reader,"state(address,uint16)",[STATE_TYPE],["address","uint16"],[address(user),0])
        return dict(zip(("quantity","entryNotionalE6","oracleE8","equityE6","cashE6","coreBlock","sizeDecimals","exists","isolated"),values))
    def spot(self,reader,user):
        balance,hold=self.get(reader,"spot(address,uint64)",["uint64","uint64"],["address","uint64"],[address(user),0])
        return {"balanceE8":balance,"holdE8":hold}
    def account(self,at,reader):
        key=(address(at),address(reader))
        if key in self.account_cache:return self.account_cache[key]
        fields={"ordersToday":"uint256","day":"uint256","lastOrderAt":"uint64","pending":"uint8","operation":"bytes32","pendingAmount":"uint256","sentCoreBlock":"uint64","sentAt":"uint64",
                "cashBefore":"int64","spotBeforeE8":"uint64","pendingBuy":"bool","cloid":"uint128","positionBeforeE8":"uint64",
                "exitKind":"uint8","setupComplete":"bool","paused":"bool","accountingQuarantined":"bool","recoveryOnly":"bool",
                "nativePrincipalE6":"uint256","costBasisE6":"uint256","unallocatedSpotE6":"uint256",
                "tradingNetE6":"int256","operatingCostE6":"uint256","profitSentE6":"uint256","availableProfit":"uint256","lastCommit":"uint64"}
        calls=[("eth_call",[{"to":address(at),"data":calldata(k+"()",[],[])},self.tag]) for k in fields]
        values=self.rpc.batch(calls)
        result={k:decode([t],raw(value))[0] for (k,t),value in zip(fields.items(),values)}
        result["operation"]="0x"+result["operation"].hex()
        result.update(account=address(at),chainId=self.rpc.chain_id,core=self.core(reader,at),spot=self.spot(reader,at),evmBlock=self.tag,evmBlockHash=self.block["hash"],timestamp=self.timestamp)
        self.account_cache[key]=result
        return result
