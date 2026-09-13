import unittest
from copy import deepcopy
from flyterm.ops.settler import collect
from flyterm.ops.venue import Venue,EvidenceIncomplete
A="0x"+"11"*20;B="0x"+"22"*20
class Snap:
    timestamp=200
    def __init__(self,state,child=0):self.s=state;self.child=child
    def account(self,*args):return self.s
    def get(self,*args):return 0
    def spot(self,*args):return {"balanceE8":self.child,"holdE8":0}
class TransferLedgerTests(unittest.TestCase):
    def base(self,kind):
        return {"pending":kind,"pendingAmount":10000000,"sentAt":100,"sentCoreBlock":10,"operation":"0x"+"33"*32,
                "core":{"coreBlock":11,"exists":True,"quantity":0,"cashE6":0,"sizeDecimals":5,"isolated":False},
                "spot":{"balanceE8":0,"holdE8":0},"spotBeforeE8":0,"cashBefore":0,"positionBeforeE8":0,"exitKind":1}
    def cfg(self):return {"addresses":{"account":A,"reader":A,"profitExit":B,"recoveryExit":B},"protocol":{"depositWallet":B}}
    def venue(self,delta):
        return Venue(transport=lambda q:[{"time":150000,"hash":"0x"+"44"*32,"delta":delta}])
    def test_deposit_dust_is_not_added_to_principal(self):
        s=self.base(1);s["spot"]["balanceE8"]=1000000001
        out=collect(Snap(s),self.cfg(),self.venue({"type":"deposit","usdc":"10"}))
        self.assertEqual(out["values"],{"creditedE6":10000000,"feeE6":0});self.assertTrue(out["evidence"]["raw"])
    def test_ambiguous_surplus_without_positive_ledger_stays_pending(self):
        s=self.base(1);s["spot"]["balanceE8"]=2000000000
        with self.assertRaises(EvidenceIncomplete):collect(Snap(s),self.cfg(),Venue(transport=lambda q:[]))
    def test_class_transfer_tolerates_extra_deposit_only_with_ledger(self):
        s=self.base(4);s["spotBeforeE8"]=1000000000;s["spot"]["balanceE8"]=1;s["core"]["cashE6"]=10000001
        out=collect(Snap(s),self.cfg(),self.venue({"type":"accountClassTransfer","usdc":"10","toPerp":True}))
        self.assertEqual(out["values"]["creditedE6"],10000000)
    def test_exit_donation_does_not_enlarge_return(self):
        s=self.base(3);s["cashBefore"]=500000000;s["core"]["cashE6"]=490000001
        out=collect(Snap(s,1000000001),self.cfg(),self.venue({"type":"send","user":A,"destination":B,"token":"USDC","sourceDex":"","destinationDex":"spot","amount":"10","fee":"0","feeToken":"USDC","nativeTokenFee":"0","nonce":1}))
        self.assertEqual(out["values"]["netE6"],10000000)
    def test_donation_from_someone_else_cannot_substitute_for_outgoing_ledger(self):
        s=self.base(3);s["cashBefore"]=500000000;s["core"]["cashE6"]=500000000
        with self.assertRaises(EvidenceIncomplete):collect(Snap(s,1000000001),self.cfg(),self.venue({"type":"send","user":B,"destination":B,"token":"USDC","sourceDex":"","destinationDex":"spot","amount":"10","fee":"0"}))
