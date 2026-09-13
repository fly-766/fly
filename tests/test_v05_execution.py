import json,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from eth_abi import decode
from flyterm.ops.planner import neural_actionable,hyper_step
from flyterm.ops.certificates import settlement_call,order_type,payload,order_tuple
from flyterm.ops.settler import collect
from flyterm.ops.venue import EvidenceIncomplete
from flyterm.ops.deployment import prepare
from flyterm.ops.configuration import keeper_config
A,B,C,D=["0x"+x*40 for x in "1234"]
ROOT=Path(__file__).resolve().parents[1]
def state(q=0):return {"day":0,"ordersToday":0,"lastOrderAt":0,"paused":False,"recoveryOnly":False,"core":{"quantity":q},"shortEnabled":True}
class V05ExecutionTests(unittest.TestCase):
 def test_action_table_and_legacy_compatibility(self):
  for q,side,expected in [(0,1,True),(0,2,True),(1,1,False),(1,2,True),(-1,1,True),(-1,2,False),(-1,0,False)]:
   self.assertEqual(neural_actionable(side,state(q),{"accountVersion":5},100),expected)
  self.assertFalse(neural_actionable(2,state(),{"accountVersion":4},100))
 def test_entries_respect_rate_limits_but_closes_remain_available(self):
  s=state();s.update(ordersToday=24,lastOrderAt=99)
  self.assertFalse(neural_actionable(2,s,{"accountVersion":5},100))
  s["core"]["quantity"]=-1;s["paused"]=True
  self.assertTrue(neural_actionable(1,s,{"accountVersion":5},100))
 def test_disabled_shorts_only_blocks_new_short_entry(self):
  s=state();s['shortEnabled']=False
  self.assertFalse(neural_actionable(2,s,{"accountVersion":5},100))
  s['core']['quantity']=-1;self.assertTrue(neural_actionable(1,s,{"accountVersion":5},100))
 def test_signed_terminal_receipt_and_versioned_payload(self):
  s={"pending":2,"sentCoreBlock":8,"pendingAmount":1000000,"cloid":1,"pendingBuy":False,"sentAt":1000,"positionBeforeE8":0,"positionBeforeSignedE8":0,"operation":"0x"+"ab"*32,"core":{"coreBlock":9,"quantity":-1000,"sizeDecimals":5,"isolated":False}}
  snap=NS(account=lambda *a:s,timestamp=1001)
  values={"status":1,"filledE8":1000000,"averagePriceE8":60000*10**8,"closedPnlE6":0,"feeE6":10000}
  venue=NS(terminal=lambda *a:(dict(values),{"kind":"fixture"},None))
  cfg={"accountVersion":5,"addresses":{"account":A,"reader":B}}
  out=collect(snap,cfg,venue);self.assertEqual(out['values']['finalPositionE8'],-1000000)
  self.assertEqual(out['message']['payload'],payload('ORDER_V05',['uint128',order_type(5)],[1,order_tuple(out['values'])]))
  data=settlement_call('settleOrder',out['values'],9,1100,'0x'+'11'*32,'0x'+'00'*65,account_version=5)
  decoded=decode([order_type(5),'uint64','uint64','bytes32','bytes'],bytes.fromhex(data[10:]));self.assertEqual(decoded[0][-1],-1000000)
  s['core']['quantity']=1000
  with self.assertRaises(EvidenceIncomplete):collect(snap,cfg,venue)
 def test_unexpected_position_is_quarantined_before_new_work(self):
  s={'pending':0,'settledPositionE8':-1000000,'accountingQuarantined':False,'core':{'quantity':0,'sizeDecimals':5}}
  cfg={'accountVersion':5,'chainId':999,'addresses':{'account':A,'reader':B}}
  self.assertEqual(hyper_step(NS(account=lambda *a:s),cfg)['kind'],'position_drift_quarantine')
 def test_v05_deployment_contains_correct_contract_and_limits(self):
  roles={k:A for k in ['xlayerDeployer','hyperDeployer','modelSigner','settlementSigner','guardian','recoveryBeneficiary']};roles.update(xlayerNonce=0,hyperNonce=0)
  manifest={'runId':'fixture','model':{'model':'fixture'},'genesisState':'11'*32}
  b=prepare(roles,D,manifest,account_version=5);self.assertEqual(b['accountVersion'],5)
  names={x['name']:x['contract'] for x in b['plans']['hyper']['transactions']};self.assertEqual(names['account'],'TradingAccountV05');self.assertEqual(names['reader'],'NativeCoreReadV05')
  protocol=json.loads((ROOT/'config/protocol-addresses.json').read_text());c=keeper_config(b,protocol,A,{'xlayer':1,'hyper':1},1,'fixture')
  self.assertFalse(c['liveEnabled']);self.assertFalse(c['mainnetCanaryAccepted']);self.assertEqual(c['chains']['hyper']['leverageCap'],20);self.assertEqual(c['policyFile'],'config/policy-v05.json')
  with self.assertRaises(ValueError):prepare(roles,D,manifest,account_version=5,trade_limits=b['tradeLimits']|{'leverageCap':21})
