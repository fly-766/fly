"""Combined Python/Solidity acceptance on an ephemeral loopback Anvil only."""
import sys,json,time,subprocess,socket,tempfile
from pathlib import Path
from eth_abi import encode,decode
from eth_utils import keccak
from eth_account import Account
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyterm.ops.rpc import Rpc
from flyterm.ops.codec import raw,calldata,object_hash,address
from flyterm.ops.deployment import predict,abi_type,prepare
from flyterm.ops.certificates import typed,sign,commit_call,settlement_call
from flyterm.ops.settler import collect
from flyterm.ops.state import Snapshot
from flyterm.ops.venue import Venue
from flyterm.ops.journal import OperationJournal
from flyterm.ops.executor import Executor
from flyterm.ops.hop import quote_to_usd0,usd0_to_quote
ROOT=Path(__file__).resolve().parents[1]
KEY=(1).to_bytes(32,"big");CERT=Account.from_key(KEY).address
def main():
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    process=subprocess.Popen(["anvil","--host","127.0.0.1","--port",str(port),"--chain-id","31337","--silent"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    rpc=Rpc("http://127.0.0.1:"+str(port),31337)
    try:
        for _ in range(100):
            try:
                if rpc.verify_chain()==31337:break
            except Exception:time.sleep(.1)
        if "anvil" not in rpc.call("web3_clientVersion",[]).lower():raise ValueError("Local Anvil required")
        sender=rpc.call("eth_accounts",[])[0];txs=[]
        xkey=(2).to_bytes(32,"big");xsigner=Account.from_key(xkey).address
        rpc.call("anvil_setBalance",[xsigner,hex(10**20)]);rpc.call("anvil_impersonateAccount",[xsigner])
        def send(to,data):
            hop_selectors={calldata(sig,[],[])[:10] for sig in ("convert(uint256,uint256,bytes)","hopProfit(uint256,bytes)","claimCreator()")}
            tx={"from":xsigner if data[:10] in hop_selectors else sender,"data":data,"gas":hex(25_000_000)}
            if to:tx["to"]=to
            h=rpc.call("eth_sendTransaction",[tx]);rec=rpc.receipt(h)
            for _ in range(100):
                if rec:break
                time.sleep(.05);rec=rpc.receipt(h)
            if rec["status"]!="0x1":raise ValueError("Local test reverted: "+str(to))
            txs.append(h);return rec
        def call(to,sig,types=(),args=()):return send(to,calldata(sig,list(types),list(args)))
        def deploy(name,args=(),source=None):
            art=json.loads((ROOT/"contracts/out"/((source or name)+".sol")/(name+".json")).read_text())
            inputs=next((x["inputs"] for x in art["abi"] if x["type"]=="constructor"),[])
            return send(None,"0x"+(raw(art["bytecode"]["object"])+encode([abi_type(p) for p in inputs],list(args))).hex())["contractAddress"]
        mock=lambda name,args=():deploy(name,args,"V03Mocks")
        ux=mock("Coin03",["X-USDC",6]);uh=mock("Coin03",["H-USDC",6]);usd0=mock("Coin03",["USDt0",6]);googl=mock("Coin03",["wGOOGLx",18]);wokb=mock("Coin03",["WOKB",18]);token=mock("Coin03",["FLY",18])
        pool=mock("Pool03",[usd0,ux]);mx=mock("Messenger03",[37]);mh=mock("Messenger03",[19]);txx=mock("Transmitter03",[ux]);txh=mock("Transmitter03",[uh])
        manager=mock("Manager03");router=mock("Router03");hop=mock("HopRouter03",[googl,usd0]);core=deploy("Core05",[uh],"V05Mocks");call(manager,"setup(address,address)",["address","address"],[token,googl])
        verifier=deploy("AttestedSettlement",[CERT]);run=b"\x01"*32;model=b"\x02"*32;gen=b"\x03"*32;st=b"\x04"*32
        registry=deploy("RunCommitRegistry",[run,model,gen,st,CERT])
        nonce=int(rpc.call("eth_getTransactionCount",[sender,"pending"]),16)
        names=["account","principalIngress","treasury","converter","buyback","recoveryVault","profitIngress","recoveryIngress"]
        a={n:predict(sender,nonce+i) for i,n in enumerate(names)}
        account=deploy("TradingAccountV05",[(uh,core,core,core,verifier,registry,mh,a["principalIngress"],a["profitIngress"],a["recoveryIngress"],a["buyback"],a["recoveryVault"],sender,37,200_000_000,2_000_000,20,24,50,100,20,1000)])
        assert account.lower()==a["account"].lower()
        a.update(reader=core,settlement=verifier,registry=registry,profitExit=predict(account,1),recoveryExit=predict(account,2))
        zero="0x"+"00"*20
        deploy("CctpIngress",[txh,uh,37,19,ux,a["treasury"],account,zero,zero])
        deploy("TaxTreasury",[ux,mx,a["converter"],account,a["principalIngress"],sender,19,2_000_000,500_000_000,1000_000_000,50])
        deploy("TaxConverter",[pool,ux,usd0,hop,hop,googl,wokb,a["treasury"],manager,token,sender,500*10**18,keccak(text="claim()")[:4],False,xsigner])
        deploy("ProfitBuyback",[pool,ux,usd0,hop,hop,googl,wokb,a["profitIngress"],sender,token,manager,router,100_000_000,500*10**18,600,500,50,xsigner])
        deploy("RecoveryVaultV04",[ux,a["recoveryIngress"],sender])
        deploy("CctpIngress",[txx,ux,19,37,uh,a["profitExit"],zero,a["buyback"],zero])
        deploy("CctpIngress",[txx,ux,19,37,uh,a["recoveryExit"],zero,zero,a["recoveryVault"]])
        vault=mock("SystemVault03",[googl,xsigner,token]);call(manager,"setVault(address,address)",["address","address"],[token,vault])
        cfg={"chainId":31337,"addresses":a,"accountVersion":5}
        venue_data={}
        def transport(q):
            if q["type"]=="userAbstraction":return "disabled"
            if q["type"]=="orderStatus":return venue_data["status"]
            if q["type"]=="userFillsByTime":return venue_data["fills"]
            raise AssertionError(q)
        venue=Venue(transport=transport);evidences=[]
        terminal=venue.terminal
        venue.terminal=lambda user,cloid,size,buy,sent:terminal(user,cloid,size,buy,sent,now_ms=Snapshot(rpc,account_version=5).timestamp*1000)
        def settle():
            snap=Snapshot(rpc,account_version=5);cert=collect(snap,cfg,venue);m=cert["message"];doc=typed("Settlement",31337,verifier,m)
            sig=sign(doc,KEY,CERT);data=settlement_call(cert["action"],cert["values"],m["coreBlock"],m["deadline"],m["evidence"],sig,account_version=5)
            send(account,data);evidences.append({"action":cert["action"],"evidenceHash":m["evidence"]})
        for u in (account,a["profitExit"],a["recoveryExit"]):call(core,"initialize(address)",["address"],[u])
        call(account,"configureCore()");call(core,"processSetup()");settle()
        call(vault,"accrue(uint256)",["uint256"],[10_000_000*10**12]);call(vault,"sync()");claimed=call(vault,"claimCreator()")
        from flyterm.ops.creator import sweep_plan
        sweep_cfg={"chainId":31337,"signerAddress":xsigner,"creatorIncome":{"manager":manager,"vault":vault,"quote":googl,"converter":a["converter"],"maxSweepWei":str(1000*10**18)}}
        sweep=sweep_plan(claimed,rpc.call("eth_getTransactionByHash",[claimed["transactionHash"]]),sweep_cfg)
        swept=rpc.call("eth_sendTransaction",[{"from":xsigner,"to":sweep["to"],"data":sweep["data"],"gas":"0x493e0"}]);assert rpc.receipt(swept)["status"]=="0x1"
        call(a["converter"],"convert(uint256,uint256,bytes)",["uint256","uint256","bytes"],[10_000_000*10**12,10_000_000*99//100,bytes.fromhex(quote_to_usd0(10_000_000*99//100)[2:])])
        snap=Snapshot(rpc,account_version=5);n=snap.get(a["treasury"],"liquidPrincipal()",["uint256"])
        call(a["treasury"],"forward(uint256,uint256)",["uint256","uint256"],[n,0]);msg=Snapshot(rpc,account_version=5).get(mx,"last()",["bytes"])
        call(a["principalIngress"],"receiveTransfer(bytes,bytes)",["bytes","bytes"],[msg,b"\xab"])
        call(account,"fund()");call(core,"processDeposit()");settle();call(account,"moveToPerp()");call(core,"processClass()");settle()
        def commit(side):
            snap=Snapshot(rpc,account_version=5);get=snap.get;n=get(registry,"nonce()",["uint64"])+1
            m={"runId":"0x"+run.hex(),"modelHash":"0x"+model.hex(),"nonce":n,"fromRound":n,"toRound":n,"observedAt":snap.timestamp,"deadline":snap.timestamp+60,
               "referencePriceE8":get(core,"price()",["uint64"]),"previousRecord":"0x"+get(registry,"recordRoot()",["bytes32"]).hex(),
               "record":"0x"+keccak(text="record"+str(n)).hex(),"previousState":"0x"+get(registry,"stateRoot()",["bytes32"]).hex(),
               "nextState":"0x"+keccak(text="state"+str(n)).hex(),"inputHash":"0x"+keccak(text="fixture").hex(),"side":side}
            send(registry,commit_call(m,sign(typed("Commit",31337,registry,m),KEY,CERT)));call(account,"execute(uint64)",["uint64"],[n])
        def fill(buy,price,status="filled",fraction=1):
            snap=Snapshot(rpc,account_version=5);state=snap.account(account,core);size=state["pendingAmount"]//fraction//1000*1000
            if status=="rejected":size=0
            old_entry=snap.core(core,account)["entryNotionalE6"];old_size=state["positionBeforeE8"]
            fee=10000 if size else 0;pnl=0 if not state["pendingReduceOnly"] or not size else (size*price//10**10-old_entry*size//old_size)*(1 if state["positionBeforeSignedE8"]>0 else -1)
            call(core,"processOrder(uint64,uint64,uint64)",["uint64","uint64","uint64"],[size,price,fee])
            stamp=Snapshot(rpc,account_version=5).timestamp*1000;cloid="0x"+state["cloid"].to_bytes(16,"big").hex();oid=len(txs)
            venue_data["status"]={"status":"order","order":{"status":status,"statusTimestamp":stamp,"order":{"coin":"BTC","side":"B" if buy else "A","cloid":cloid,"oid":oid,"origSz":str(state["pendingAmount"]/1e8)}}}
            venue_data["fills"]=[] if not size else [{"coin":"BTC","side":"B" if buy else "A","oid":oid,"tid":oid,"time":stamp,"sz":str(size/1e8),"px":str(price/1e8),"closedPnl":str(pnl/1e6),"fee":str(fee/1e6),"feeToken":"USDC"}]
            settle()
        commit(1);fill(True,100*10**8);call(core,"setPrice(uint64)",["uint64"],[110*10**8]);commit(2);fill(False,110*10**8)
        rpc.call("evm_increaseTime",[21]);rpc.call("evm_mine",[])
        commit(2);fill(False,110*10**8)
        assert Snapshot(rpc,account_version=5).core(core,account)["quantity"]<0
        call(core,"setPrice(uint64)",["uint64"],[100*10**8]);commit(1);fill(True,100*10**8)
        assert Snapshot(rpc,account_version=5).core(core,account)["quantity"]==0
        profit=Snapshot(rpc,account_version=5).get(account,"availableProfit()",["uint256"]);assert profit>5_000_000
        call(account,"requestExit(uint256,bool)",["uint256","bool"],[5_000_000,False]);call(core,"processTransfer()");settle()
        call(a["profitExit"],"bridgeToEvm()");call(core,"processTransfer()");call(a["profitExit"],"reconcileEvm()");call(a["profitExit"],"burnReturn(uint256)",["uint256"],[0])
        msg=Snapshot(rpc,account_version=5).get(mh,"last()",["bytes"]);call(a["profitIngress"],"receiveTransfer(bytes,bytes)",["bytes","bytes"],[msg,b"\xab"])
        call(a["buyback"],"convertProfit(uint256)",["uint256"],[5_000_000]);call(a["buyback"],"hopProfit(uint256,bytes)",["uint256","bytes"],[1,bytes.fromhex(usd0_to_quote(1)[2:])]);call(a["buyback"],"observe()");rpc.call("evm_increaseTime",[601]);rpc.call("evm_mine",[]);call(a["buyback"],"observe()");call(a["buyback"],"buyback(uint256)",["uint256"],[10**18])
        escrow=Snapshot(rpc,account_version=5).get(a["buyback"],"escrowedTokens()",["uint256"]);assert escrow>0
        # Production prepare() emits constructors for the exact ABI and deterministic nonces.
        manifest_path=ROOT/"runs/v03-live-observation/manifest.json"
        manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {"runId":"local-fixture","model":{"model":"test"},"genesisState":"01"*32}
        roles={k:sender for k in ("xlayerDeployer","hyperDeployer","guardian","recoveryBeneficiary")};roles.update(modelSigner=CERT,settlementSigner=CERT,xlayerNonce=10,hyperNonce=20)
        bundle=prepare(roles,token,manifest,account_version=5);assert len(bundle["plans"]["xlayer"]["transactions"])==6
        # Optional transaction executor is exercised with a public fixture key on this Anvil only.
        rpc.call("anvil_setBalance",[CERT,hex(10**20)])
        config={"chainId":31337,"signerAddress":CERT,"liveEnabled":True,"allowedCalls":{a["buyback"].lower():["0x"+keccak(text="observe()")[:4].hex()]},
                "maxCallValueWei":"0","maxGasUnits":1000000,"maxGasPriceWei":"100000000000","maxDailyGasWei":str(10**19),"confirmations":1}
        rpc.call("evm_increaseTime",[601]);rpc.call("evm_mine",[])
        with tempfile.TemporaryDirectory() as tmp:
            j=OperationJournal(Path(tmp)/"ops.sqlite")
            e=Executor(config,j,rpc,lambda:KEY);out=e.submit("observe",{"chainId":31337,"to":a["buyback"],"value":"0","data":calldata("observe()",[],[])},live=True,approved_hash=object_hash(config))
            for _ in range(100):
                result=e.reconcile(out["id"])
                if result["state"]=="CONFIRMED":break
                time.sleep(.05)
            assert result["state"]=="CONFIRMED";j.close()
        # Run the real Keeper decision loop through TWO further tax-to-Core cycles.
        # Only the external Core and Circle networks are replaced by asynchronous local fixtures.
        from flyterm.ops.configuration import keeper_config
        from flyterm.ops.keeper import Keeper
        import os
        protocol={"xlayer":{"chainId":31337,"domain":37,"usdc":ux,"usd0":usd0,"quote":googl,"wgooglx":googl,"wokb":wokb,"hopRouter":hop,"hopSpender":hop,"manager":manager},"hyper":{"chainId":31337,"domain":19,"usdc":uh}}
        local_bundle={"addresses":a,"projectToken":token,"taxVault":vault,"accountVersion":5,"tradeLimits":{"leverageCap":20,"reserveBps":1000,"maxOrderE6":200_000_000,"lossStopE6":2_000_000},"roles":{"modelSigner":CERT,"settlementSigner":CERT}}
        profile=keeper_config(local_bundle,protocol,CERT,{"xlayer":0,"hyper":0},0,"unused-local-run")
        profile.update(liveEnabled=True,mainnetCanaryAccepted=True,localFixtureOnly=True)
        profile["chains"]["xlayer"]["creatorIncome"]["maxSweepWei"]=str(500*10**18)
        xkey=(2).to_bytes(32,"big");xsigner=Account.from_key(xkey).address
        rpc.call("anvil_setBalance",[xsigner,hex(10**20)]);profile["chains"]["xlayer"]["signerAddress"]=xsigner
        for c in profile["chains"].values():
            c.update(liveEnabled=True,confirmations=1,maxGasPriceWei="100000000000",maxDailyGasWei=str(10**19))
            c.pop("okxQuotes",None);c["requiredReadCodePins"]=[]
            c["runtimeCodeHashes"]={addr:"0x"+keccak(raw(rpc.code(addr))).hex() for addr in c["allowedCalls"]}
            os.environ[c["rpcEnv"]]="http://127.0.0.1:"+str(port)
        for route in profile["routes"]:route["confirmations"]=1
        auto_events=[]
        with tempfile.TemporaryDirectory() as tmp:
            keeper=Keeper(profile,tmp,live=True,approved=object_hash(profile))
            try:
                for name,e in keeper.executors.items():e.key_loader=(lambda key=xkey if name=="xlayer" else KEY:key)
                keeper._key=lambda name:KEY
                keeper.venue=Venue(transport=lambda q:[] if q["type"]=="userFunding" else transport(q))
                def circle_fixture(url):
                    m=Snapshot(rpc,account_version=5).get(mx if "/messages/37?" in url else mh,"last()",["bytes"])
                    return {"messages":[{"status":"complete","message":"0x"+m.hex(),"attestation":"0xab"}]}
                keeper.cctp.transport=circle_fixture;processed=set()
                for cycle in range(2):
                    call(vault,"accrue(uint256)",["uint256"],[50_000_000*10**12])
                    target_basis=60_000_000+cycle*50_000_000
                    for tick in range(120):
                        out=keeper.step();auto_events.append({k:v for k,v in out.items() if k in ("chain","kind","state","reason")})
                        rpc.call("evm_mine",[])
                        state=Snapshot(rpc,account_version=5).account(account,core);op=state["operation"]
                        if state["pending"] in (1,3,4) and op not in processed:
                            call(core,{1:"processDeposit()",3:"processTransfer()",4:"processClass()"}[state["pending"]]);processed.add(op)
                        if out.get("kind") in ("profitExit_to_evm","recoveryExit_to_evm") and out.get("state")=="SUBMITTED":call(core,"processTransfer()")
                        if state["costBasisE6"]==target_basis and not state["pending"] and not state["nativePrincipalE6"] and not state["unallocatedSpotE6"]:break
                    else:raise AssertionError(("Keeper did not complete tax cycle",cycle,auto_events[-12:],state["costBasisE6"],state["pending"]))
                for chain,c in profile["chains"].items():
                    for pending in keeper.j.pending(c["chainId"],c["signerAddress"]):
                        assert keeper.executors[chain].reconcile(pending["id"])["state"]=="CONFIRMED"
                kinds=[e.get("kind") for e in auto_events]
                assert kinds.count("creator_tax_claim")==2 and kinds.count("creator_tax_sweep")==2 and kinds.count("fund")==2,(kinds,"new cycles must not reuse completed operations")
            finally:keeper.close()
        coupled=None
        if "--with-model" in sys.argv:
            from flyterm.live import LiveBrain,replay as replay_live
            from flyterm.records import digest
            import copy
            run_name=sys.argv[sys.argv.index("--model-run")+1] if "--model-run" in sys.argv else "v03-coupled-model"
            run_dir=ROOT/"runs"/run_name
            brain=LiveBrain(run_dir,policy_path=ROOT/"config/policy-v05.json");assert not brain.rows,"Coupled acceptance requires a fresh run"
            manifest=brain.manifest
            reg2=deploy("RunCommitRegistry",[raw("0x"+digest(manifest["runId"]),32),raw("0x"+digest(manifest["model"]),32),raw("0x"+digest(manifest),32),raw("0x"+manifest["genesisState"],32),CERT])
            fly2=mock("Coin03",["MODEL-FLY",18]);call(manager,"setup(address,address)",["address","address"],[fly2,googl])
            n=int(rpc.call("eth_getTransactionCount",[sender,"pending"]),16)
            a2={name:predict(sender,n+i) for i,name in enumerate(names)}
            acc2=deploy("TradingAccountV05",[(uh,core,core,core,verifier,reg2,mh,a2["principalIngress"],a2["profitIngress"],a2["recoveryIngress"],a2["buyback"],a2["recoveryVault"],sender,37,200_000_000,2_000_000,20,24,50,100,20,1000)])
            a2.update(reader=core,settlement=verifier,registry=reg2,profitExit=predict(acc2,1),recoveryExit=predict(acc2,2))
            deploy("CctpIngress",[txh,uh,37,19,ux,a2["treasury"],acc2,zero,zero])
            deploy("TaxTreasury",[ux,mx,a2["converter"],acc2,a2["principalIngress"],sender,19,2_000_000,500_000_000,1000_000_000,50])
            deploy("TaxConverter",[pool,ux,usd0,hop,hop,googl,wokb,a2["treasury"],manager,fly2,sender,500*10**18,keccak(text="claim()")[:4],False,xsigner])
            deploy("ProfitBuyback",[pool,ux,usd0,hop,hop,googl,wokb,a2["profitIngress"],sender,fly2,manager,router,100_000_000,500*10**18,600,500,50,xsigner])
            deploy("RecoveryVaultV04",[ux,a2["recoveryIngress"],sender])
            deploy("CctpIngress",[txx,ux,19,37,uh,a2["profitExit"],zero,a2["buyback"],zero])
            deploy("CctpIngress",[txx,ux,19,37,uh,a2["recoveryExit"],zero,zero,a2["recoveryVault"]])
            vault2=mock("ClaimVault03",[googl,a2["converter"]]);call(manager,"setVault(address,address)",["address","address"],[fly2,vault2])
            for u in (acc2,a2["profitExit"],a2["recoveryExit"]):call(core,"initialize(address)",["address"],[u])
            cfg2=keeper_config({"addresses":a2,"projectToken":fly2,"accountVersion":5,"tradeLimits":{"leverageCap":20,"reserveBps":1000,"maxOrderE6":200_000_000,"lossStopE6":2_000_000},"roles":{"modelSigner":CERT,"settlementSigner":CERT}},protocol,CERT,{"xlayer":0,"hyper":0},0,str(run_dir))
            cfg2.update(liveEnabled=True,mainnetCanaryAccepted=True,localFixtureOnly=True)
            cfg2["chains"]["xlayer"]["signerAddress"]=xsigner
            for c in cfg2["chains"].values():
                c.update(liveEnabled=True,confirmations=1,maxGasPriceWei="100000000000",maxDailyGasWei=str(10**19))
                c.pop("okxQuotes",None);c["requiredReadCodePins"]=[]
                c["runtimeCodeHashes"]={addr:"0x"+keccak(raw(rpc.code(addr))).hex() for addr in c["allowedCalls"]}
            for route in cfg2["routes"]:route["confirmations"]=1
            observed_fills=[];model_ops=[];processed2=set();venue2=Venue(transport=lambda q:[] if q["type"]=="userFunding" else transport(q))
            terminal2=venue2.terminal
            venue2.terminal=lambda user,cloid,size,buy,sent:terminal2(user,cloid,size,buy,sent,now_ms=Snapshot(rpc,account_version=5).timestamp*1000)
            def settle_external_fixture(execution_kind=None):
                state=Snapshot(rpc,account_version=5).account(acc2,core);op=state["operation"]
                if op in processed2:return
                if state["pending"] in (1,4,5):
                    call(core,{1:"processDeposit()",4:"processClass()",5:"processSetup()"}[state["pending"]]);processed2.add(op)
                elif state["pending"]==2:
                    size=state["pendingAmount"];price=state["core"]["oracleE8"];buy=state["pendingBuy"];fee=size*price//10**10*45//100000
                    pnl=0 if not state["pendingReduceOnly"] else (size*price//10**10-state["core"]["entryNotionalE6"]*size//state["positionBeforeE8"])*(1 if state["positionBeforeSignedE8"]>0 else -1)
                    call(core,"processOrder(uint64,uint64,uint64)",["uint64","uint64","uint64"],[size,price,fee])
                    stamp=Snapshot(rpc,account_version=5).timestamp*1000;cloid="0x"+state["cloid"].to_bytes(16,"big").hex();oid=len(txs)
                    venue_data["status"]={"status":"order","order":{"status":"filled","statusTimestamp":stamp,"order":{"coin":"BTC","side":"B" if buy else "A","cloid":cloid,"oid":oid,"origSz":str(size/1e8)}}}
                    venue_data["fills"]=[{"coin":"BTC","side":"B" if buy else "A","oid":oid,"tid":oid,"time":stamp,"sz":str(size/1e8),"px":str(price/1e8),"closedPnl":str(pnl/1e6),"fee":str(fee/1e6),"feeToken":"USDC"}]
                    observed_fills.append({"side":"BUY" if buy else "SELL","reduceOnly":state["pendingReduceOnly"],"positionBeforeE8":state["positionBeforeSignedE8"],"executionKind":execution_kind,"sizeE8":size,"feeE6":fee,"closedPnlE6":pnl});processed2.add(op)
            with tempfile.TemporaryDirectory() as tmp:
                k=Keeper(cfg2,tmp,live=True,approved=object_hash(cfg2))
                try:
                    for name,e in k.executors.items():e.key_loader=(lambda key=xkey if name=="xlayer" else KEY:key)
                    k._key=lambda name:KEY;k.venue=venue2;k.cctp.transport=circle_fixture
                    call(vault2,"accrue(uint256)",["uint256"],[10_000_000*10**12])
                    for step in range(100):
                        out=k.step();rpc.call("evm_mine",[]);settle_external_fixture(out.get("kind"))
                        st2=Snapshot(rpc,account_version=5).account(acc2,core)
                        if st2["costBasisE6"]==10_000_000 and not st2["pending"] and not st2["nativePrincipalE6"] and not st2["unallocatedSpotE6"]:break
                    else:raise AssertionError("Coupled account funding stalled")
                    markets=json.loads((ROOT/"runs/v03-archived-markets.json").read_text())
                    current_market={};observe_real=brain.observe
                    brain.observe=lambda snapshot:observe_real(snapshot,current_market)
                    k.brain=brain
                    for index,original in enumerate(markets[:16]):
                        rpc.call("evm_increaseTime",[60]);rpc.call("evm_mine",[])
                        call(core,"setPrice(uint64)",["uint64"],[int(round(original["markPrice"]*1e8))])
                        stamp=Snapshot(rpc,account_version=5).timestamp;current_market=copy.deepcopy(original)
                        shift=stamp*1000-int(original["providerTime"]*1000)
                        for candle in current_market["candles"]:
                            candle["time"]+=shift;candle["closeTime"]+=shift
                        current_market.update(providerTime=stamp,fetchedAt=stamp,source="saved public candles retimed to local Anvil clock",originalProviderTime=original["providerTime"],localFixtureOnly=True)
                        for step in range(30):
                            out=k.step();model_ops.append({key:value for key,value in out.items() if key in ("kind","state","reason")})
                            rpc.call("evm_mine",[]);settle_external_fixture(out.get("kind"))
                            if out.get("reason")=="next_completed_market_bar" or out.get("state")=="OBSERVED" or out.get("hyper")=="paused_or_recovery_only":break
                        else:raise AssertionError("Coupled model step stalled")
                        if not brain.rows:raise AssertionError("No model observation produced")
                        print(json.dumps({"coupledRound":index+1,"actualNeuralSide":brain.rows[-1]["body"]["neural"]["side"],"settledOrders":len(observed_fills)}),flush=True)
                        if out.get("hyper")=="paused_or_recovery_only":break
                    model_order_count=len(observed_fills)
                    call(acc2,"pause()")
                    for _ in range(20):
                        out=k.step();rpc.call("evm_mine",[]);settle_external_fixture("test_end_cleanup" if out.get("kind")=="emergencyClose" else out.get("kind"))
                        cleanup=Snapshot(rpc,account_version=5).account(acc2,core)
                        if cleanup["core"]["quantity"]==0 and not cleanup["pending"]:break
                    else:raise AssertionError("Test account did not finish flat and settled")
                    for chain,c in cfg2["chains"].items():
                        for pending in k.j.pending(c["chainId"],c["signerAddress"]):assert k.executors[chain].reconcile(pending["id"])["state"]=="CONFIRMED"
                    assert any(f["side"]=="BUY" for f in observed_fills)
                    assert any(f["side"]=="SELL" for f in observed_fills)
                    assert any(row["body"]["reinforcement"]!="none" for row in brain.rows[1:])
                    assert Snapshot(rpc,account_version=5).get(reg2,"lastRound()",["uint64"])>0
                    coupled={"rounds":len(brain.rows),"modelOrderCount":model_order_count,"cleanupOrderCount":len(observed_fills)-model_order_count,"finalPositionE8":0,"finalEquityE6":cleanup["core"]["equityE6"],"tradingNetE6":cleanup["tradingNetE6"],"pausedAtEnd":cleanup["paused"],"actualModelOutputs":True,"modelRunId":manifest["runId"],"fills":observed_fills,"keeperTransitions":model_ops,
                             "fixtureNote":"Actual full brain and actual Keeper/contract code; historical public prices retimed to Anvil, external venue/Circle execution simulated."}
                finally:k.close()
            expected_state=brain.brain.state_fingerprint();brain.close()
            restored=LiveBrain(run_dir,policy_path=ROOT/"config/policy-v05.json");assert restored.brain.state_fingerprint()==expected_state;restored.close()
            coupled["restartRestoresExactState"]=True
            coupled["fullReplay"]=replay_live(run_dir)
            (ROOT/"evidence/v05-coupled-model.json").write_text(json.dumps(coupled,indent=2))
        report={"schema":"flyterm-local-acceptance/v05","accountVersion":5,"leverageCap":20,"initialFixturePrincipalE6":10000000,"directedShortCycle":True,"passed":True,"network":"ephemeral Anvil 31337 only","realBroadcast":False,"transactions":sum(int(rpc.call("eth_getTransactionCount",[who,"latest"]),16) for who in (sender,CERT,xsigner)),"manualFixtureTransactions":len(txs),"certificateSettlements":evidences,
            "profitEligibleE6":profit,"returnedProfitE6":5_000_000,"escrowedTokens":str(escrow),"directedTestSignals":True,"creatorTaxInterface":"creatorOwed/sync/claimCreator","creatorSweepReceiptVerified":True,"keeperCycles":2,"coupledModel":coupled,"keeperTransitions":auto_events,
            "scope":"Python ABI, EIP712, native snapshot collector, terminal venue fixtures, Solidity money route and durable executor together; real external Core/CCTP acceptance remains separate"}
        (ROOT/"evidence/v05-local-acceptance.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:process.terminate();process.wait(timeout=10)
if __name__=="__main__":main()
