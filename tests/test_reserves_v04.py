import unittest,copy
from eth_abi import decode
from flyterm.ops.reserves import reserve_step,bridge_fee_e8
A="0x"+"11"*20;B="0x"+"22"*20;U="0x"+"33"*20;R="0x"+"44"*20;E="0x"+"55"*20
class FakeSnapshot:
    tag="0x1";block={"baseFeePerGas":hex(100000000)}
    def __init__(self):
        self.state={"paused":True,"recoveryOnly":True,"pending":0,"nativePrincipalE6":0,"unallocatedSpotE6":0,"core":{"quantity":0,"cashE6":0}}
        self.usdc=0;self.hype=10000;self.hold=0;self.evm_hype=0;self.core_usdc=0;self.stage=0
        self.rpc=self;self.chain_id=999
    def account(self,*a):return self.state
    def get(self,at,sig,outputs,*a):
        if sig=="guardian()":return B
        if sig=="stage()":return self.stage
        if sig=="balanceOf(address)":return self.usdc
        if sig=="spot(address,uint64)":return self.hype,self.hold
        raise AssertionError(sig)
    def spot(self,*a):return {"balanceE8":self.core_usdc,"holdE8":0}
    def call(self,method,args):
        assert method=="eth_getBalance";return hex(self.evm_hype)
class ReservePlanTests(unittest.TestCase):
    def setUp(self):
        self.s=FakeSnapshot();self.c={"addresses":{"account":A,"reader":R,"profitExit":E,"recoveryExit":U},"protocol":{"usdc":U}}
    def args(self,out):return decode(["uint64","uint256","bool"],bytes.fromhex(out["intent"]["data"][10:]))
    def test_fixed_guardian_and_usdc_priority(self):
        self.s.usdc=1;out=reserve_step(self.s,self.c,"account")
        self.assertEqual(self.args(out),(0,1,False));self.assertEqual(out["expectedSigner"],B);self.assertFalse(out["signingEnabled"])
        self.s.usdc=0;self.s.core_usdc=100;self.s.evm_hype=10**12
        out=reserve_step(self.s,self.c,"account");self.assertEqual(self.args(out),(0,100,True))
    def test_usdc_fee_is_reserved_but_native_hype_is_swept_fully(self):
        self.assertEqual(bridge_fee_e8(100000000),2250)
        out=reserve_step(self.s,self.c,"account");self.assertEqual(self.args(out),(150,10000,True))
        self.s.hype=2000
        self.assertEqual(self.args(reserve_step(self.s,self.c,"account")),(150,2000,True))
    def test_live_principal_profit_or_pending_state_blocks_sweep(self):
        for field in ("pending","nativePrincipalE6","unallocatedSpotE6"):
            self.s=FakeSnapshot();self.s.state[field]=1
            with self.assertRaises(ValueError):reserve_step(self.s,self.c,"account")
        for field in ("quantity","cashE6"):
            self.s=FakeSnapshot();self.s.state["core"][field]=1
            with self.assertRaises(ValueError):reserve_step(self.s,self.c,"account")
        self.s=FakeSnapshot();self.s.state["paused"]=False
        with self.assertRaises(ValueError):reserve_step(self.s,self.c,"account")
    def test_pending_exit_and_missing_fee_do_not_create_intents(self):
        self.s.stage=3;self.assertIn("wait",reserve_step(self.s,self.c,"profitExit"))
        self.s.stage=0;self.s.block={};self.s.core_usdc=100
        with self.assertRaises(ValueError):reserve_step(self.s,self.c,"account")

    def test_sub_native_unit_usdc_is_reported_before_draining_gas(self):
        self.s.core_usdc=99
        out=reserve_step(self.s,self.c,"account")
        self.assertEqual(out["wait"],"usdc_precision_dust");self.assertEqual(out["topupToNativeUnitE8"],1)
