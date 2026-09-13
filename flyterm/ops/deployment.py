"""Pure deterministic deployment preparation. Never queries keys, signs or submits."""
import json,rlp
from pathlib import Path
from eth_abi import encode
from eth_utils import keccak
from .codec import address,raw,calldata,object_hash
ROOT=Path(__file__).resolve().parents[2]
ZERO="0x"+"00"*20
def predict(sender,nonce):return address("0x"+keccak(rlp.encode([raw(address(sender),20),int(nonce)]))[-20:].hex())
def abi_type(p):
    if p["type"].startswith("tuple"):return "("+",".join(abi_type(c) for c in p["components"])+")"+p["type"][5:]
    return p["type"]
def creation(name,args):
    a=json.loads((ROOT/"contracts/out"/(name+".sol")/(name+".json")).read_text())
    inputs=next((x["inputs"] for x in a["abi"] if x["type"]=="constructor"),[])
    code=raw(a["bytecode"]["object"]);return "0x"+(code+encode([abi_type(p) for p in inputs],args)).hex()
def prepare(roles,project_token,run_manifest,protocol=None,account_version=4,trade_limits=None):
    p=protocol or json.loads((ROOT/"config/protocol-addresses.json").read_text());x=p["xlayer"];h=p["hyper"];c=p["cctp"]
    for k in ("xlayerDeployer","hyperDeployer","modelSigner","settlementSigner","guardian","recoveryBeneficiary"):address(roles[k])
    token=address(project_token);xn=int(roles["xlayerNonce"]);hn=int(roles["hyperNonce"])
    if min(xn,hn)<0:raise ValueError("Negative nonce")
    xnames=["converter","treasury","buyback","recoveryVault","profitIngress","recoveryIngress"]
    hnames=["reader","settlement","registry","account","principalIngress"]
    xa={n:predict(roles["xlayerDeployer"],xn+i) for i,n in enumerate(xnames)}
    ha={n:predict(roles["hyperDeployer"],hn+i) for i,n in enumerate(hnames)}
    ha["profitExit"]=predict(ha["account"],1);ha["recoveryExit"]=predict(ha["account"],2)
    addr={**xa,**ha};g=roles["guardian"]
    model_hash="0x"+object_hash(run_manifest["model"]);run_id="0x"+object_hash(run_manifest["runId"])
    genesis="0x"+object_hash(run_manifest);state=raw("0x"+run_manifest["genesisState"],32)
    constructor={
      "converter":("TaxConverter",[x["stablePool"],x["usdc"],x["usd0"],x["hopRouter"],x["hopSpender"],x["wgooglx"],x["wokb"],xa["treasury"],x["manager"],token,g,5*10**18,keccak(text="claim()")[:4],False,roles["xlayerDeployer"]]),
      "treasury":("TaxTreasury",[x["usdc"],c["messenger"],xa["converter"],ha["account"],ha["principalIngress"],g,h["domain"],10_000_000,1000_000_000,5000_000_000,100]),
      "buyback":("ProfitBuyback",[x["stablePool"],x["usdc"],x["usd0"],x["hopRouter"],x["hopSpender"],x["wgooglx"],x["wokb"],xa["profitIngress"],g,token,x["manager"],x["router"],1000_000_000,5*10**18,600,1000,50,roles["xlayerDeployer"]]),
      "recoveryVault":("RecoveryVaultV04",[x["usdc"],xa["recoveryIngress"],roles["recoveryBeneficiary"]]),
      "profitIngress":("CctpIngress",[c["transmitter"],x["usdc"],h["domain"],x["domain"],h["usdc"],ha["profitExit"],ZERO,xa["buyback"],ZERO]),
      "recoveryIngress":("CctpIngress",[c["transmitter"],x["usdc"],h["domain"],x["domain"],h["usdc"],ha["recoveryExit"],ZERO,ZERO,xa["recoveryVault"]]),
      "reader":("NativeCoreRead",[]),
      "settlement":("AttestedSettlement",[roles["settlementSigner"]]),
      "registry":("RunCommitRegistry",[raw(run_id,32),raw(model_hash,32),raw(genesis,32),state,roles["modelSigner"]]),
      "account":("TradingAccountV04",[(h["usdc"],ha["reader"],h["writer"],h["depositWallet"],ha["settlement"],ha["registry"],c["messenger"],ha["principalIngress"],xa["profitIngress"],xa["recoveryIngress"],xa["buyback"],xa["recoveryVault"],g,x["domain"],100_000_000,200_000_000,20,24,50,100)]),
      "principalIngress":("CctpIngress",[c["transmitter"],h["usdc"],x["domain"],h["domain"],x["usdc"],xa["treasury"],ha["account"],ZERO,ZERO])
    }
    if account_version not in (4,5):raise ValueError("Unsupported account version")
    limits=trade_limits or {"leverageCap":20,"reserveBps":1000,"maxOrderE6":200_000_000,"lossStopE6":2_000_000}
    if account_version==5:
        if not 1<=int(limits["leverageCap"])<=20 or not 1000<=int(limits["reserveBps"])<=5000 or int(limits["maxOrderE6"])<10_000_000 or int(limits["lossStopE6"])<=0:raise ValueError("Invalid reviewed trade limits")
        constructor["reader"]=("NativeCoreReadV05",[])
        args=list(constructor["account"][1][0]);args[14]=int(limits["maxOrderE6"]);args[15]=int(limits["lossStopE6"])
        constructor["account"]=("TradingAccountV05",[tuple(args+[int(limits["leverageCap"]),int(limits["reserveBps"])])])
    plans={}
    for chain,names,nonce,sender in [("xlayer",xnames,xn,roles["xlayerDeployer"]),("hyper",hnames,hn,roles["hyperDeployer"])]:
        rows=[]
        for i,key in enumerate(names):
            name,args=constructor[key];data=creation(name,args)
            rows.append({"name":key,"contract":name,"predictedAddress":addr[key],"intent":{"chainId":p[chain]["chainId"],"to":None,"value":"0","expectedNonce":nonce+i,"data":data},"creationHash":"0x"+keccak(raw(data)).hex()})
        plans[chain]={"signer":address(sender),"chainId":p[chain]["chainId"],"transactions":rows}
    return {"schema":"flyterm-deployment/v05" if account_version==5 else "flyterm-deployment/v04","accountVersion":account_version,"tradeLimits":limits if account_version==5 else None,"withdrawalPolicy":{"artificialDelaySeconds":0,"requiresFlatAndSettled":True,"fixedBeneficiary":roles["recoveryBeneficiary"],"reserveRecovery":{"assets":["USDC","HYPE"],"onlyAfterFullShutdown":True,"beneficiary":roles["guardian"],"erc20CoreBridgeGasMustBeReserved":True,"nativeHypeCoreBridgeFeeE8":0}},"liveEnabled":False,"addresses":addr,"projectToken":token,"roles":roles,"runId":run_id,"modelHash":model_hash,"genesisRecord":genesis,"plans":plans,
            "notes":["Predictions are valid only for the listed deployer nonces.","Run genesis must exist before registry deployment.","Webpage System Vault launch: 1% tax to the creator, quote wGOOGLx, hop GOOGL to OKB to USD then CCTP.","OKX unsigned quotes require pinned router and spender, bounded slippage, simulation and a fresh accepted live profile.","All deployed dependencies and nonce/code hashes must be checked before signing."]}
