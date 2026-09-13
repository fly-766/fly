"""Generate an unarmed keeper profile from a reviewed deployment receipt map."""
from eth_utils import keccak
from .codec import address,object_hash
def selector(sig):return "0x"+keccak(text=sig)[:4].hex()
def keeper_config(bundle,protocol,keeper,from_blocks,funding_from_ms,run_dir):
    a=bundle["addresses"];token=bundle["projectToken"];chains={}
    calls={
      "xlayer":{"converter":["claim()","convert(uint256,uint256,bytes)"],"treasury":["forward(uint256,uint256)"],"buyback":["convertProfit(uint256)","hopProfit(uint256,bytes)","observe()","buyback(uint256)","flushEscrow()"],"profitIngress":["receiveTransfer(bytes,bytes)"],"recoveryIngress":["receiveTransfer(bytes,bytes)"]},
      "hyper":{"account":["configureCore()","fund()","moveToPerp()","execute(uint64)","emergencyClose()","requestExit(uint256,bool)",
        "settleSetup(uint64,uint64,bytes32,bytes)","settleDeposit(uint64,uint64,uint64,uint64,bytes32,bytes)","settleClassTransfer(uint64,uint64,uint64,uint64,bytes32,bytes)",
        "settleExit(uint64,uint64,uint64,uint64,bytes32,bytes)","settleOrder((uint8,uint64,uint64,int256,uint64,uint64),uint64,uint64,bytes32,bytes)",
        "bookCost(bytes32,int256,bool,uint64,uint64,bytes32,bytes)"],
        "registry":["submit((uint64,uint64,uint64,uint64,uint64,uint64,bytes32,bytes32,bytes32,bytes32,bytes32,uint8),bytes)"],
        "profitExit":["bridgeToEvm()","reconcileEvm()","burnReturn(uint256)"],"recoveryExit":["bridgeToEvm()","reconcileEvm()","burnReturn(uint256)"],"principalIngress":["receiveTransfer(bytes,bytes)"]}}
    immediate=bundle.get("withdrawalPolicy",{}).get("artificialDelaySeconds")==0
    if immediate:calls["xlayer"]["recoveryVault"]=["withdraw()"]
    for chain in ("xlayer","hyper"):
        chains[chain]={"chainId":protocol[chain]["chainId"],"signerAddress":address(keeper),"signerKeyFileEnv":"FLYTERM_KEEPER_KEY_FILE","rpcEnv":"FLYTERM_"+chain.upper()+"_RPC",
            "withdrawConfirmedPrincipal":immediate and chain=="xlayer","liveEnabled":False,"allowedCalls":{a[n].lower():[selector(s) for s in signatures] for n,signatures in calls[chain].items()},
            "runtimeCodeHashes":{},"requireCodePins":True,"maxCallValueWei":"0","maxGasUnits":1500000,"maxGasPriceWei":"2000000000","maxDailyGasWei":"50000000000000000","confirmations":12,
            "addresses":a,"projectToken":token,"protocol":protocol[chain],"bridgeMaxFeeBps":10,"bridgeMaxFeeE6":1000000,
            "minimumConversionE6":1000000,"minimumBuybackE6":1000000,"maxBuybackE6":1000000,"minimumProfitE6":10000000,"maxProfitBatchE6":100000000,
            "fundingFromMs":int(funding_from_ms),"anchorEveryRounds":16,"minimumQuoteWei":10**15,"maxQuoteWei":5*10**18,"minimumBuybackQuoteWei":10**15,"maxBuybackQuoteWei":10**18}
    routes=[]
    for kind,source,dest,sender,recipient,ingress in [(0,"xlayer","hyper","treasury","account","principalIngress"),(1,"hyper","xlayer","profitExit","buyback","profitIngress"),(2,"hyper","xlayer","recoveryExit","recoveryVault","recoveryIngress")]:
        routes.append({"kind":kind,"sourceChain":source,"destinationChain":dest,"sourceDomain":protocol[source]["domain"],"destinationDomain":protocol[dest]["domain"],
            "destinationChainId":protocol[dest]["chainId"],"sourceSender":a[sender],"messageSender":a[sender],"burnToken":protocol[source]["usdc"],"mintRecipient":a[recipient],
            "destinationCaller":a[ingress],"fromBlock":int(from_blocks[source]),"confirmations":12})
    return {"schema":"flyterm-keeper/v03","liveEnabled":False,"runDirectory":str(run_dir),"chains":chains,"routes":routes,
        "modelSigner":bundle["roles"]["modelSigner"],"modelKeyFileEnv":"FLYTERM_MODEL_KEY_FILE",
        "settlementSigner":bundle["roles"]["settlementSigner"],"settlementKeyFileEnv":"FLYTERM_SETTLEMENT_KEY_FILE",
        "gasPolicy":"externally sponsored; excluded from strategy PnL unless separately booked as operating cost",
        "budgetStatus":"draft ceilings; review before arming","mainnetCanaryAccepted":False}
