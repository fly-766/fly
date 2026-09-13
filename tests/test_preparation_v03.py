import unittest,json,copy,tempfile
from pathlib import Path
from eth_abi import decode,encode
from eth_utils import keccak
from flyterm.ops.launch import request,validate_response,vault_data,PARAMS,WGOOGLX
from flyterm.ops.codec import calldata,raw
from flyterm.ops.creator import sweep_plan,TRANSFER
from flyterm.ops.configuration import keeper_config
from flyterm.ops.deployment import prepare,predict
from flyterm.ops.planner import xlayer_step
ROOT=Path(__file__).resolve().parents[1]
A="0x"+"11"*20;B="0x"+"22"*20;C="0x"+"33"*20;D="0x"+"44"*20
class PreparationTests(unittest.TestCase):
    def make(self):
        req=request({"taxBuyBps":100,"taxSellBps":100,"name":"FlyTerm","symbol":"FLY","metadataURI":"ipfs://reviewed-metadata","graduationProtectionDays":7,"firstBuy":"0"},A,WGOOGLX)
        params={n:0 for n,t in PARAMS};params.update({k:v for k,v in req.items() if k in params})
        params.update(salt="0x"+"12"*32,founderRoot="0x"+"00"*32,graduation=str(20*10**18),listingFee="1000000",buyFeeBps=100,sellFeeBps=100,firstBuy="0",quote=WGOOGLX)
        resp={"params":params,"templateId":0,"vaultData":vault_data(0),"deadline":2000000000,"factory":D,"venue":1,"graduationProtectionSecs":604800,"signature":"0x"+"ab"*65,"tokenAddress":D}
        limits={"factory":D,"venue":1,"maxListingFeeRaw":1000000,"graduationRaw":20*10**18,"maxPlatformFeeBps":100,"expectedToken":D}
        return req,resp,limits
    def test_launch_parameters_and_tax_destination_bound(self):
        req,res,limits=self.make();self.assertEqual(req["templateId"],0);self.assertEqual(req["taxRecipients"],[])
        out=validate_response(res,req,limits,A);self.assertEqual(out["quoteApprovalE6"],"1000000");self.assertFalse(out["signingEnabled"])
        res["vaultData"]=vault_data(10000)
        with self.assertRaises(ValueError):validate_response(res,req,limits,A)
    def test_unknown_taxes_and_unexpected_founder_rejected(self):
        with self.assertRaises(ValueError):request({"taxBuyBps":None},A,WGOOGLX)
        with self.assertRaises(ValueError):request({"taxBuyBps":200,"taxSellBps":100,"name":"FlyTerm","symbol":"FLY"},A,WGOOGLX)
        req,res,limits=self.make();res["params"]["founderBps"]=1
        with self.assertRaises(ValueError):validate_response(res,req,limits,A)
    def test_platform_fee_quote_and_prediction_checked(self):
        for key,value in [("quote",B),("taxSellBps",200),("firstBuy","1"),("listingFee","1000001")]:
            req,res,limits=self.make();res["params"][key]=value
            with self.assertRaises(ValueError):validate_response(res,req,limits,A)
    def test_creator_sweep_only_claim_delta_fixed_recipient(self):
        cfg={"chainId":196,"signerAddress":A,"creatorIncome":{"manager":B,"quote":C,"converter":D,"maxSweepE6":1000000}}
        word=lambda a:"0x"+"00"*12+a[2:]
        receipt={"status":"0x1","transactionHash":"0x"+"12"*32,"blockHash":"0x"+"34"*32,"logs":[{"address":C,"topics":[TRANSFER,word(B),word(A)],"data":"0x"+(50000).to_bytes(32,"big").hex()}]}
        tx={"from":A,"to":B,"input":calldata("claimCreatorFees(address)",["address"],[C])}
        out=sweep_plan(receipt,tx,cfg);to,amount=decode(["address","uint256"],raw(out["data"])[4:])
        self.assertEqual(to.lower(),D);self.assertEqual(amount,50000)
        with self.assertRaises(ValueError):sweep_plan(receipt,tx|{"to":D},cfg)
    def test_deployment_nonced_addresses_and_disabled_profile(self):
        manifest=json.loads((ROOT/"runs/v03-live-observation/manifest.json").read_text()) if (ROOT/"runs/v03-live-observation/manifest.json").exists() else {"runId":"fixture","model":{"model":"test"},"genesisState":"01"*32}
        roles={k:A for k in ("xlayerDeployer","hyperDeployer","modelSigner","settlementSigner","guardian","recoveryBeneficiary")}
        roles.update(xlayerNonce=0,hyperNonce=0)
        b=prepare(roles,D,manifest);self.assertEqual(b["addresses"]["account"],predict(A,3));self.assertEqual(b["addresses"]["profitExit"],predict(b["addresses"]["account"],1))
        self.assertEqual(b["schema"],"flyterm-deployment/v04");self.assertEqual(b["withdrawalPolicy"]["artificialDelaySeconds"],0)
        by_name={tx["name"]:tx for plan in b["plans"].values() for tx in plan["transactions"]}
        self.assertEqual(by_name["account"]["contract"],"TradingAccountV04");self.assertEqual(by_name["recoveryVault"]["contract"],"RecoveryVaultV04")
        protocol=json.loads((ROOT/"config/protocol-addresses.json").read_text());cfg=keeper_config(b,protocol,A,{"xlayer":1,"hyper":2},1,"runs/example")
        self.assertFalse(cfg["liveEnabled"]);self.assertFalse(cfg["mainnetCanaryAccepted"]);self.assertEqual(len(cfg["routes"]),3)
        for c in cfg["chains"].values():self.assertEqual(c["maxCallValueWei"],"0");self.assertFalse(c["liveEnabled"])
        self.assertTrue(cfg["chains"]["xlayer"]["withdrawConfirmedPrincipal"]);self.assertFalse(cfg["chains"]["hyper"]["withdrawConfirmedPrincipal"])
        vault=b["addresses"]["recoveryVault"]
        self.assertIn("0x"+keccak(text="withdraw()")[:4].hex(),cfg["chains"]["xlayer"]["allowedCalls"][vault.lower()])
        for plan in b["plans"].values():
            for t in plan["transactions"]:
                self.assertEqual(t["creationHash"],"0x"+keccak(raw(t["intent"]["data"])).hex())

    def test_confirmed_principal_has_fixed_immediate_withdrawal_action(self):
        class Snapshot:
            def get(self,at,signature,outputs,*rest):
                if at==B and signature=="credited()":return 12_000_000
                raise AssertionError("Confirmed principal should be returned before unrelated new work")
        cfg={"addresses":{"recoveryVault":B,"converter":A,"buyback":C,"treasury":D},"protocol":{},"chainId":196,"projectToken":D,"withdrawConfirmedPrincipal":True}
        out=xlayer_step(Snapshot(),cfg)
        self.assertEqual(out["kind"],"principal_withdraw")
        self.assertEqual(out["intent"],{"chainId":196,"to":B,"value":"0","data":calldata("withdraw()",[],[])})
