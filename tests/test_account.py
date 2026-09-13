import unittest
from flyterm.account import ShadowAccount,ShadowGuard,D

P={"biasWindow":3,"lossStopUsdc":"200","slippage":"0","feeRate":"0","maxOrderUsdc":"100","minimumNotionalUsdc":"10"}
def market(price=100):
    return {"ok":True,"markPrice":price,"bid":price,"ask":price,"sizeDecimals":5,"stale":False}
class AccountTests(unittest.TestCase):
    def test_deposit_is_principal_not_profit(self):
        a=ShadowAccount("100");a.deposit("200")
        self.assertEqual(a.distributable(),0);self.assertEqual(a.principal,300)
    def test_futures_open_does_not_spend_notional(self):
        a=ShadowAccount("500");a.transact("BUY","1","100","0")
        self.assertEqual(a.collateral,500);self.assertEqual(a.equity("110"),510)
        a.transact("SELL","1","110","0")
        self.assertEqual(a.collateral,510);self.assertEqual(a.distributable(),10)
    def test_losses_recovered_before_profit_and_no_double_distribution(self):
        a=ShadowAccount("500");a.transact("BUY",1,100,0);a.transact("SELL",1,90,0)
        a.transact("BUY",1,100,0);a.transact("SELL",1,115,0)
        self.assertEqual(a.distributable(),5)
        a.distribute(5);self.assertEqual(a.distributable(),0)
        with self.assertRaises(ValueError):a.distribute(1)
    def test_unrealized_gains_cannot_be_distributed(self):
        a=ShadowAccount("500");a.transact("BUY",1,100,0)
        self.assertEqual(a.equity(200),600);self.assertEqual(a.distributable(),0)
    def test_loss_guard_closes_even_when_neural_says_buy(self):
        a=ShadowAccount("500");a.transact("BUY",4,100,0)
        r=ShadowGuard(P).execute(a,{"side":"BUY"},market(40),calibration_passed=True)
        self.assertEqual(r["source"],"risk");self.assertEqual(r["side"],"SELL")
        self.assertEqual(a.quantity,0);self.assertTrue(a.halted)
    def test_bias_blocks_opening_not_exit(self):
        a=ShadowAccount("500");g=ShadowGuard(P,["BUY","BUY"])
        self.assertEqual(g.execute(a,{"side":"BUY"},market(),calibration_passed=True)["reason"],"persistent_directional_bias")
        a.transact("BUY",1,100,0)
        self.assertEqual(g.execute(a,{"side":"SELL"},market())["status"],"SHADOW_FILLED")
    def test_unaccepted_calibration_never_opens(self):
        a=ShadowAccount();r=ShadowGuard(P).execute(a,{"side":"BUY"},market())
        self.assertEqual(r["reason"],"calibration_not_accepted");self.assertEqual(a.quantity,0)
    def test_no_short_and_one_x_cap(self):
        a=ShadowAccount("100")
        with self.assertRaises(ValueError):a.transact("SELL",1,100,0)
        with self.assertRaises(ValueError):a.transact("BUY",2,100,0)
