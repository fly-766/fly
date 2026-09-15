"""Bounded scheduler regression checks; no keys, RPC or transactions."""
import unittest,time
from unittest.mock import Mock,patch
from scripts import bsc_live_scheduler as m
class Checks(unittest.TestCase):
 def setUp(self):
  self.k=m.Keeper.__new__(m.Keeper);self.k.config={'chains':{'hyper':{'chainId':999,'signerAddress':'0x'+'11'*20,'accountVersion':5,'addresses':{'account':'0x'+'22'*20,'registry':'0x'+'33'*20},'anchorEveryRounds':8}}};self.k.rpcs={'hyper':object()};self.k.j=Mock();self.k.j.pending.return_value=[];self.k.brain=Mock();self.k._submit=Mock(return_value='EXECUTED');self.k._submit_model=Mock(return_value='COMMITTED');self.k._model_actionable=Mock(side_effect=lambda s,c,state,side:side in (1,2));self.k.live=True
  self.state={'core':{'equityE6':18914868},'lastCommit':0};self.snap=Mock(timestamp=int(time.time()));self.snap.get.side_effect=lambda at,sig,types: {'nonce()':0,'side()':0,'deadline()':int(time.time())+60}[sig]
  self.fresh=Mock(timestamp=int(time.time())+1);self.plan={'wait':'model_observation','snapshot':self.state};self.k.brain.commit.return_value={'side':2,'fromRound':1,'toRound':2}
  patch.object(m,'Snapshot',side_effect=[self.snap,self.fresh]).start();self.hp=patch.object(m,'hyper_step',return_value=self.plan).start();patch.object(m.BaseKeeper,'step',return_value='BASE').start()
 def tearDown(self):patch.stopall()
 def test_refresh_and_short(self):
  self.assertEqual(self.k.step(),'COMMITTED');self.k.brain.commit.assert_called_once_with(self.fresh,self.k.config['chains']['hyper'])
 def test_pending_first(self):
  self.k.j.pending.return_value=[{'id':'pending'}];self.assertEqual(self.k.step(),'BASE');self.k.brain.observe.assert_not_called()
 def test_settlement_first(self):
  self.hp.return_value={'wait':'venue_settlement'};self.assertEqual(self.k.step(),'BASE');self.k.brain.observe.assert_not_called()
 def test_hold_allows_transport(self):
  self.k.brain.commit.return_value={'side':0,'fromRound':1,'toRound':2};self.assertEqual(self.k.step(),'BASE');self.k._submit_model.assert_not_called()
 def test_existing_commit_first(self):
  self.snap.get.side_effect=lambda at,sig,types:{'nonce()':1,'side()':2,'deadline()':int(time.time())+60}[sig];self.assertEqual(self.k.step(),'EXECUTED');self.k.brain.observe.assert_not_called()
 def test_once_per_window(self):
  self.k._model_window=int(time.time())//60;self.assertEqual(self.k.step(),'BASE');self.k.brain.observe.assert_not_called()
 def test_changed_account_after_brain(self):
  self.hp.side_effect=[self.plan,{'wait':'venue_settlement'}];self.assertEqual(self.k.step(),'BASE');self.k.brain.commit.assert_not_called()
if __name__=='__main__':unittest.main()
