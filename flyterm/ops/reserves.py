"""Unsigned reserve cleanup for the fixed guardian after the trading account is drained."""
from .planner import action
from .codec import address
def bridge_fee_e8(base_fee_wei,buffer_bps=1250):
    base=int(base_fee_wei)
    if base<=0 or not 0<=buffer_bps<=5000:raise ValueError("Invalid Core-to-EVM fee quote")
    denominator=10000*10**10
    return (200000*base*(10000+buffer_bps)+denominator-1)//denominator
def reserve_step(snap,cfg,holder_key):
    a=cfg["addresses"]
    if holder_key not in ("account","profitExit","recoveryExit"):raise ValueError("Unknown reserve holder")
    account=a["account"];holder=a[holder_key];reader=a["reader"];usdc=cfg["protocol"]["usdc"]
    state=snap.account(account,reader)
    if not state["paused"] or state["pending"] or state["nativePrincipalE6"] or state["unallocatedSpotE6"] or state["core"]["quantity"] or state["core"]["cashE6"]:
        raise ValueError("Finish principal, profit and pending operations before reserve cleanup")
    if holder_key!="account" and snap.get(holder,"stage()",["uint8"])!=0:
        return {"wait":"exit_has_reserved_funds"}
    guardian=address(snap.get(account,"guardian()",["address"]))
    def plan(token,amount,core,kind):
        out=action(snap.rpc.chain_id,holder,"recoverReserves(uint64,uint256,bool)",["uint64","uint256","bool"],[token,amount,core],kind)
        return out|{"expectedSigner":guardian,"expectedBeneficiary":guardian,"signingEnabled":False,"amount":amount,"token":token,"fromCore":core}
    native_usdc=snap.get(usdc,"balanceOf(address)",["uint256"],["address"],[holder])
    if native_usdc:return plan(0,native_usdc,False,"reserve_usdc_to_guardian")
    spot_usdc=snap.spot(reader,holder)
    core_usdc=max(0,spot_usdc["balanceE8"]-spot_usdc["holdE8"])
    hype_balance,hype_hold=snap.get(reader,"spot(address,uint64)",["uint64","uint64"],["address","uint64"],[holder,150])
    free_hype=max(0,hype_balance-hype_hold)
    if core_usdc>=100:
        raw_fee=snap.block.get("baseFeePerGas")
        if raw_fee is None:raise ValueError("Missing EVM base fee")
        fee=bridge_fee_e8(int(raw_fee,16) if isinstance(raw_fee,str) else raw_fee)
        if free_hype<fee:return {"wait":"core_bridge_gas_insufficient","requiredHypeE8":fee}
        return plan(0,core_usdc//100*100,True,"reserve_usdc_to_evm")|{"reservedHypeFeeE8":fee}
    native_hype=int(snap.rpc.call("eth_getBalance",[holder,snap.tag]),16)
    if native_hype:return plan(150,native_hype,False,"reserve_hype_to_guardian")
    if spot_usdc["holdE8"] or hype_hold:return {"wait":"held_core_reserves"}
    if core_usdc:return {"wait":"usdc_precision_dust","coreUsdcPrecisionDustE8":core_usdc,"topupToNativeUnitE8":100-core_usdc}
    # Native HYPE is credited as the EVM gas asset, not an ERC20 transfer.
    # Live send-asset receipts establish zero nativeTokenFee for this path.
    if free_hype:return plan(150,free_hype,True,"reserve_hype_to_evm")|{"reservedHypeFeeE8":0}
    return {"wait":"reserve_cleanup_complete","remainingCoreHypeE8":0,"coreUsdcPrecisionDustE8":0}
