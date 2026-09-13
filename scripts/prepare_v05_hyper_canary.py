"""Prepare a Hyper-only, user-executed canary. No RPC, keys, signing or broadcast."""
import argparse,json,sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eth_utils import keccak
from flyterm.ops.codec import address,raw,object_hash,calldata
from flyterm.ops.deployment import creation,predict,ROOT

def prepare(operator,guardian,nonce,manifest,principal_e6=10_000_000):
    operator=address(operator);guardian=address(guardian);nonce=int(nonce);principal_e6=int(principal_e6)
    if operator==guardian or nonce<0 or not 2_000_000<=principal_e6<=50_000_000:raise ValueError("Invalid two-wallet canary parameters")
    p=json.loads((ROOT/'config/protocol-addresses.json').read_text())['hyper']
    names=['reader','settlement','registry','recoveryVault','routes','account']
    a={name:predict(operator,nonce+i) for i,name in enumerate(names)}
    a.update(profitExit=predict(a['account'],1),recoveryExit=predict(a['account'],2))
    values={
      'reader':('NativeCoreReadV05',[]),
      'settlement':('AttestedSettlement',[operator]),
      'registry':('RunCommitRegistry',[raw('0x'+object_hash(manifest['runId']),32),raw('0x'+object_hash(manifest['model']),32),raw('0x'+object_hash(manifest),32),raw('0x'+manifest['genesisState'],32),operator]),
      'recoveryVault':('RecoveryVaultV04',[p['usdc'],a['routes'],guardian]),
      'routes':('CanaryFundingRoutes',[p['usdc'],operator,a['account'],a['profitExit'],a['recoveryExit'],a['recoveryVault'],guardian,principal_e6]),
      'account':('TradingAccountV05',[(p['usdc'],a['reader'],p['writer'],p['depositWallet'],a['settlement'],a['registry'],a['routes'],a['routes'],a['routes'],a['routes'],guardian,a['recoveryVault'],guardian,19,200_000_000,2_000_000,20,4,50,0,20,1000)])}
    transactions=[]
    for i,name in enumerate(names):
        contract,args=values[name];data=creation(contract,args)
        transactions.append({'name':name,'contract':contract,'predictedAddress':a[name],'intent':{'chainId':999,'to':None,'data':data,'value':'0','expectedNonce':nonce+i},'creationHash':'0x'+keccak(raw(data)).hex()})
    return {'schema':'fly-manual-hyper-canary/v05','state':'UNSIGNED_REVIEW_REQUIRED','signingEnabled':False,'broadcastEnabled':False,'liveEnabled':False,
      'chainId':999,'operator':operator,'guardian':guardian,'addresses':a,'principalCapE6':principal_e6,'leverageCap':20,'reserveBps':1000,'maxOrderE6':200_000_000,'lossStopTriggerE6':2_000_000,
      'transactions':transactions,'fundingIntents':[
        {'chainId':999,'to':p['usdc'],'value':'0','data':calldata('approve(address,uint256)',['address','uint256'],[a['routes'],principal_e6])},
        {'chainId':999,'to':a['routes'],'value':'0','data':calldata('fundPrincipal(uint256)',['uint256'],[principal_e6])}],
      'scope':'Hyper-only trading and fixed-beneficiary recovery; no tax/CCTP/token-buyback claim',
      'prerequisites':['Refresh deployer nonce before use','Inspect exact creation bytecode and role bindings','Review HYPE gas and separate Core activation fees','Activate account and both exit addresses, verify disabled abstraction and native BTC leverage 20','Use a new valid neural commitment; do not fabricate a SELL','User reviews and signs every financial action','Finish flat, settled and paused']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--operator',required=True);ap.add_argument('--guardian',required=True);ap.add_argument('--nonce',required=True,type=int);ap.add_argument('--manifest',required=True,type=Path);ap.add_argument('--principal-usdc',default='10');ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
    n=Decimal(a.principal_usdc)*1_000_000
    if n!=n.to_integral_value():raise ValueError('USDC precision exceeds six decimals')
    plan=prepare(a.operator,a.guardian,a.nonce,json.loads(a.manifest.read_text()),int(n));a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'state':plan['state'],'deploymentTransactions':len(plan['transactions']),'principalCapE6':plan['principalCapE6'],'signingEnabled':False,'broadcastEnabled':False}))
