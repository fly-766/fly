import unittest,tempfile,copy,json
from pathlib import Path
from eth_account import Account
from eth_utils import keccak
from eth_abi import encode
from flyterm.ops.executor import Executor,NotArmed
from flyterm.ops.journal import OperationJournal
from flyterm.ops.codec import object_hash,calldata,decode_cctp
from flyterm.ops.venue import Venue,EvidenceIncomplete
from flyterm.ops.certificates import typed,sign,recover
KEY=(1).to_bytes(32,"big") # Public test fixture. Never funded.
USER=Account.from_key(KEY).address
TARGET="0x"+"22"*20
class FakeRpc:
    chain_id=31337
    def __init__(self):self.sent=[];self.fail_send=False;self.receipts={};self.head=10;self.hash="0x"+"aa"*32;self.fail_preflight=False
    def verify_chain(self):return 31337
    def receipt(self,h):return self.receipts.get(h)
    def call(self,m,p):
        if m=="eth_call":
            if self.fail_preflight:raise ValueError("Revert")
            return "0x"
        if m=="eth_estimateGas":return hex(21000)
        if m=="eth_getTransactionCount":return "0x0"
        if m=="eth_gasPrice":return "0x2"
        if m=="eth_blockNumber":return hex(self.head)
        if m=="eth_getBlockByNumber":return {"hash":self.hash}
        if m=="eth_sendRawTransaction":
            self.sent.append(p[0])
            if self.fail_send:raise TimeoutError("Response lost")
            return "0x"+keccak(bytes.fromhex(p[0][2:])).hex()
        raise AssertionError(m)
class OpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.j=OperationJournal(Path(self.tmp.name)/"ops.sqlite");self.rpc=FakeRpc();self.key_reads=0
        self.config={"chainId":31337,"signerAddress":USER,"liveEnabled":True,"allowedCalls":{TARGET:["0x12345678"]},
                     "maxCallValueWei":"100","maxGasUnits":100000,"maxGasPriceWei":"100","maxDailyGasWei":"1000000","confirmations":2}
        def key():self.key_reads+=1;return KEY
        self.e=Executor(self.config,self.j,self.rpc,key)
        self.intent={"chainId":31337,"to":TARGET,"data":"0x12345678","value":"0"}
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def submit(self):return self.e.submit("test",self.intent,live=True,approved_hash=object_hash(self.config))
    def receipt(self,h,status=1):
        return {"transactionHash":h,"status":hex(status),"blockNumber":"0x9","blockHash":self.rpc.hash,"gasUsed":hex(21000),"effectiveGasPrice":"0x2"}
    def test_plan_never_reads_key_or_broadcasts(self):
        out=self.e.submit("test",self.intent);self.assertFalse(out["signingEnabled"]);self.assertEqual(self.key_reads,0);self.assertEqual(self.rpc.sent,[])
    def test_exact_config_gate_and_allowlist(self):
        with self.assertRaises(NotArmed):self.e.submit("test",self.intent,live=True,approved_hash="old")
        with self.assertRaises(ValueError):self.e.submit("test",self.intent|{"data":"0x87654321"})
        self.assertEqual(self.key_reads,0)
    def test_direct_dispatch_requires_matching_code_pins_before_key(self):
        self.config["requireCodePins"]=True
        with self.assertRaises(NotArmed):self.submit()
        self.assertEqual(self.key_reads,0)
        self.config["runtimeCodeHashes"]={TARGET:"0x"+keccak(bytes.fromhex("6000")).hex()}
        self.rpc.batch=lambda calls:["0x6001"]
        with self.assertRaises(NotArmed):self.submit()
        self.assertEqual(self.key_reads,0)
        self.rpc.batch=lambda calls:["0x6000"]
        self.assertEqual(self.submit()["state"],"SUBMITTED")
    def test_preflight_before_key(self):
        self.rpc.fail_preflight=True
        with self.assertRaises(ValueError):self.submit()
        self.assertEqual(self.key_reads,0)
    def test_uncertain_send_persisted_resume_same_bytes(self):
        self.rpc.fail_send=True;out=self.submit()
        self.assertEqual(out["state"],"UNKNOWN");attempts=self.j.attempts(out["id"]);self.assertEqual(len(attempts),1)
        self.rpc.fail_send=False;self.e.resume(out["id"],approved_hash=object_hash(self.config))
        self.assertEqual(self.rpc.sent[0],self.rpc.sent[1]);self.assertEqual(self.key_reads,1)
    def test_replacement_preserves_intent_and_original_hash_can_mine(self):
        out=self.submit();self.e.resume(out["id"],approved_hash=object_hash(self.config),replace=True)
        attempts=self.j.attempts(out["id"]);self.assertEqual(len(attempts),2);self.assertGreater(attempts[1]["price"],attempts[0]["price"])
        self.rpc.receipts[out["txHash"]]=self.receipt(out["txHash"])
        self.assertEqual(self.e.reconcile(out["id"])["state"],"CONFIRMED")
    def test_pending_serializes_same_wallet_not_other_wallet(self):
        out=self.submit()
        with self.assertRaises(NotArmed):self.e.submit("second",self.intent|{"data":"0x1234567800"},live=True,approved_hash=object_hash(self.config))
        second=self.j.plan(31337,"0x"+"33"*20,object_hash(self.config),"test",self.intent);self.j.signed(second["id"],0,"0xab","0xother",1,1)
    def test_reorg_clears_receipt_and_reserves_gas(self):
        out=self.submit();self.rpc.receipts[out["txHash"]]=self.receipt(out["txHash"]);self.rpc.head=9
        self.assertEqual(self.e.reconcile(out["id"])["state"],"MINED")
        self.rpc.hash="0x"+"bb"*32
        self.assertEqual(self.e.reconcile(out["id"])["state"],"UNKNOWN");self.assertIsNone(self.j.get(out["id"])["receipt"])
        self.assertEqual(self.j.daily_gas(31337,USER),25200*2)
    def test_daily_budget_includes_native_value(self):
        self.config["maxDailyGasWei"]="50450";self.intent["value"]="100"
        with self.assertRaises(NotArmed):self.submit()
        self.assertEqual(self.key_reads,0)
    def test_deployment_nonce_binding(self):
        self.config["allowedDeployments"]=["0x"+keccak(b"\x60\x00").hex()]
        self.intent={"chainId":31337,"to":None,"data":"0x6000","expectedNonce":1}
        with self.assertRaises(NotArmed):self.submit()
        self.assertEqual(self.key_reads,0)
    def test_same_calldata_in_new_cycle_has_its_own_operation(self):
        self.intent["operationContext"]="0x"+"11"*32;out=self.submit()
        self.rpc.receipts[out["txHash"]]=self.receipt(out["txHash"]);self.e.reconcile(out["id"])
        # Model RPC nonce advancement after first mined transaction.
        old_call=self.rpc.call
        self.rpc.call=lambda m,p:"0x1" if m=="eth_getTransactionCount" else old_call(m,p)
        self.intent["operationContext"]="0x"+"22"*32;later=self.submit()
        self.assertNotEqual(later["id"],out["id"]);self.assertEqual(len(self.rpc.sent),2)
    def test_certificate_domain_and_signer_binding(self):
        m={"account":USER,"operation":"0x"+"01"*32,"payload":"0x"+"02"*32,"coreBlock":20,"deadline":1000,"evidence":"0x"+"03"*32}
        doc=typed("Settlement",31337,TARGET,m);sig=sign(doc,KEY,USER);self.assertEqual(recover(doc,sig),USER)
        self.assertNotEqual(recover(typed("Settlement",196,TARGET,m),sig),USER)
class VenueTests(unittest.TestCase):
    def make(self,state="filled",fills=None,cloid="0x"+"12"*16):
        order={"coin":"BTC","side":"B","cloid":cloid,"oid":20,"origSz":"0.001"}
        status={"status":"order","order":{"status":state,"statusTimestamp":2000,"order":order}}
        sample={"coin":"BTC","side":"B","oid":20,"tid":1,"time":2000,"sz":"0.001","px":"100000","closedPnl":"0","fee":"0.045","feeToken":"USDC"}
        return Venue(transport=lambda q:status if q["type"]=="orderStatus" else ([sample] if fills is None else fills)),status
    def test_full_order_and_fee(self):
        v,_=self.make();r,_,_=v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
        self.assertEqual(r["filledE8"],100000);self.assertEqual(r["feeE6"],45000)
    def test_unknown_oid_never_zero_fill(self):
        v=Venue(transport=lambda q:{"status":"unknownOid"})
        with self.assertRaises(EvidenceIncomplete):v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
    def test_filled_missing_fills_rejected(self):
        v,_=self.make(fills=[])
        with self.assertRaises(EvidenceIncomplete):v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
    def test_cancel_zero_fill_valid(self):
        v,_=self.make(state="canceled",fills=[]);r,_,_=v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
        self.assertEqual(r["status"],2);self.assertEqual(r["filledE8"],0)
    def test_official_ioc_rejection_is_terminal(self):
        v,_=self.make(state="iocCancelRejected",fills=[])
        receipt,_,_=v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
        self.assertEqual(receipt["status"],3);self.assertEqual(receipt["filledE8"],0)
    def test_wrong_identity_and_time(self):
        v,s=self.make();s["order"]["order"]["side"]="A"
        with self.assertRaises(EvidenceIncomplete):v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
    def test_conflicting_fill_ids_fail(self):
        sample={"coin":"BTC","side":"B","oid":20,"tid":1,"time":2000,"sz":"0.001","px":"100000","closedPnl":"0","fee":"0","feeToken":"USDC"}
        v,_=self.make(fills=[sample,sample|{"px":"99999"}])
        with self.assertRaises(EvidenceIncomplete):v.terminal(USER,"0x"+"12"*16,100000,True,1000,3000)
class CctpTests(unittest.TestCase):
    def msg(self):
        b=bytearray(536)
        def put(p,v,n=32):b[p:p+n]=int(v).to_bytes(n,"big")
        put(0,1,4);put(4,37,4);put(8,19,4);put(12,1);put(144,2000,4);put(148,1,4)
        for p in (108,152,184,248):put(p,int(TARGET,16))
        put(216,1000000);put(280,1000);put(312,100)
        b[376:]=encode(["bytes4","uint8","uint256","uint64","bytes32"],[b"FT03",0,1000000,1,b"\0"*32]);return b
    def test_decode_exact_route_and_net(self):
        t=decode_cctp("0x"+self.msg().hex());self.assertEqual(t["amount"]-t["fee"],999900);self.assertEqual(t["sourceDomain"],37)
    def test_malformed_version_finality_and_fee(self):
        for p,v,n in [(0,2,4),(144,1000,4),(312,2000,32)]:
            b=self.msg();b[p:p+n]=v.to_bytes(n,"big")
            with self.assertRaises(ValueError):decode_cctp("0x"+b.hex())
