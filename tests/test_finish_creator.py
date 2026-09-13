import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from flyterm.ops.creator import creator_step,sweep_plan,TRANSFER
from flyterm.ops.codec import calldata
from flyterm.ops.journal import OperationJournal
A,B,C,D,E,F=["0x"+x*40 for x in "123456"]
CFG={"chainId":196,"signerAddress":A,"projectToken":E,"addresses":{"converter":D},"creatorIncome":{"manager":F,"vault":B,"quote":C,"converter":D,"minimumClaimWei":"10","maxSweepWei":"1000"}}
TX={"from":A,"to":B,"input":calldata("claimCreator()",[],[])}
def receipt():return {"status":"0x1","transactionHash":"0x"+"11"*32,"blockHash":"0x"+"22"*32,"blockNumber":"0x1","logs":[{"address":C,"topics":[TRANSFER,"0x"+B[2:].zfill(64),"0x"+A[2:].zfill(64)],"data":"0x"+hex(25)[2:].zfill(64)}]}
class Snap:
 def __init__(self,owed=20,balance=30):self.owed=owed;self.balance=balance;self.rpc=SimpleNamespace(call=lambda *a:TX)
 def get(self,at,sig,outputs,*args):
  return {"vaultOf(address)":B,"CREATOR()":A,"QUOTE()":C,"TOKEN()":E,"DIVIDEND_BPS()":0,"paused()":False,"creatorOwed()":self.owed,"balanceOf(address)":self.balance}[sig]
class CreatorTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.j=OperationJournal(Path(self.tmp.name)/"ops.sqlite")
 def tearDown(self):self.j.close();self.tmp.cleanup()
 def test_claim_real_vault_not_manager_fee_bucket(self):
  out=creator_step(Snap(),CFG,self.j);self.assertEqual(out["kind"],"creator_tax_claim");self.assertEqual(out["intent"]["to"],B);self.assertEqual(out["intent"]["data"],TX["input"])
 def test_sync_only_above_threshold_and_budget(self):
  self.assertIsNone(creator_step(Snap(owed=0,balance=1),CFG,self.j));self.assertEqual(creator_step(Snap(owed=0,balance=30),CFG,self.j)["kind"],"creator_tax_sync")
  with self.assertRaises(ValueError):creator_step(Snap(owed=2000,balance=2000),CFG,self.j)
 def test_sweep_only_actual_vault_transfer(self):
  out=sweep_plan(receipt(),TX,CFG);self.assertEqual(out["to"],C)
  with self.assertRaises(ValueError):sweep_plan(receipt(),TX|{"to":F,"input":calldata("claimCreatorFees(address)",["address"],[C])},CFG)
  r=receipt();r["logs"][0]["topics"][1]="0x"+F[2:].zfill(64)
  with self.assertRaises(ValueError):sweep_plan(r,TX,CFG)
 def test_restart_resumes_same_sweep_and_never_consumes_claim_twice(self):
  row=self.j.plan(196,A,"test","creator_tax_claim",{"to":B,"data":TX["input"]})
  self.j.db.execute("UPDATE ops SET state='CONFIRMED',receipt=? WHERE id=?",(json.dumps(receipt()),row["id"]));self.j.db.commit()
  plan=creator_step(Snap(),CFG,self.j);self.assertEqual(plan["kind"],"creator_tax_sweep")
  saved=self.j.plan(196,A,"test",plan["kind"],plan["intent"])
  self.assertEqual(creator_step(Snap(),CFG,self.j),plan)
  self.j.state(saved["id"],"CONFIRMED")
  self.assertNotEqual(creator_step(Snap(),CFG,self.j)["kind"],"creator_tax_sweep")
  with self.assertRaises(ValueError):self.j.plan(196,A,"test","creator_tax_sweep",plan["intent"]|{"value":"1"})
 def test_failed_sweep_requires_reconciliation(self):
  row=self.j.plan(196,A,"test","creator_tax_claim",{"to":B});self.j.db.execute("UPDATE ops SET state='CONFIRMED',receipt=? WHERE id=?",(json.dumps(receipt()),row["id"]));self.j.db.commit()
  plan=creator_step(Snap(),CFG,self.j);saved=self.j.plan(196,A,"test",plan["kind"],plan["intent"]);self.j.state(saved["id"],"REVERTED")
  with self.assertRaises(ValueError):creator_step(Snap(),CFG,self.j)
