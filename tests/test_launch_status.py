import json,time,unittest
from unittest.mock import patch
from eth_abi import encode
from eth_utils import keccak
from flyterm.launch_status import load_instance,live_status,public_status,_CACHE
A,B,C,D,E,F=["0x"+c*40 for c in "123456"]
CFG={"published":True,"officialProduct":True,"role":"production","chainId":196,"token":A,"creator":B,"vault":C,"quote":D,"manager":E,"registry":F,"expectedFactory":F,"templateId":0,"taxBuyBps":100,"taxSellBps":100,"dividendBps":0,"createTx":"0x"+"ab"*32,"rpcPublic":"https://fixture.invalid"}
class LaunchStatusTests(unittest.TestCase):
 def fixture(self,**changes):
  sig=lambda s:"0x"+keccak(text=s)[:4].hex()
  types=["address","uint16","uint16","uint16","uint16","address","uint16","uint16","uint64","uint128","uint128","uint128","uint128","uint128","uint128","bytes32"]
  values=[B,100,100,100,100,D,0,0,1,1,1,1,1,1,1,b"\x00"*32]
  def rpc(url,method,params):
   if method=="eth_chainId":return changes.get("chain","0xc4")
   if method=="eth_getBlockByNumber":return {"number":"0x100","hash":"0x"+"11"*32,"timestamp":hex(int(time.time())-changes.get("age",0))}
   if method=="eth_getTransactionReceipt":
    topic="0x"+keccak(text="TokenCreated(address,address,address,uint256,string,address,address,uint16)").hex()
    return {"status":"0x1","blockNumber":"0x10","blockHash":"0x"+changes.get("blockHashByte","11")*32,"logs":[{"address":E,"topics":[topic,*["0x"+x[2:].zfill(64) for x in (A,B,D)]],"data":"0x"+encode(["uint256","string","address","address","uint16"],[20,"uri",C,F,changes.get("template",0)]).hex()}]}
   sel=params[0]["data"][:10];maps={"tokens(address)":(types,values),"vaultOf(address)":(["address"],[changes.get("vault",C)]),"factoryOf(uint16)":(["address"],[changes.get("factory",F)]),"DIVIDEND_BPS()":(["uint16"],[changes.get("dividend",0)]),"CREATOR()":(["address"],[B]),"TOKEN()":(["address"],[A]),"QUOTE()":(["address"],[D]),"pairOf(address)":(["address"],[changes.get("pair","0x"+"00"*20)]),"creatorOwed()":(["uint256"],[123]),"creatorAccrued(address,address)":(["uint256"],[0]),"balanceOf(address)":(["uint256"],[456])}
   for name,(ts,vs) in maps.items():
    if sel==sig(name):return "0x"+encode(ts,vs).hex()
   raise AssertionError(sel)
  return rpc
 def test_default_unpublished_never_calls_rpc(self):
  self.assertFalse(load_instance()["published"])
  with patch("flyterm.launch_status._rpc",side_effect=AssertionError("network")):
   self.assertFalse(public_status()["published"])
 def test_real_checks_and_separate_income_fields(self):
  with patch("flyterm.launch_status._rpc",self.fixture()):out=live_status(instance=CFG)
  self.assertTrue(out["ok"]);self.assertTrue(out["officialProduct"]);self.assertEqual(out["creatorTaxOwedWei"],"123");self.assertEqual(out["managerCreatorFeesWei"],"0")
 def test_template_registry_identity_reorg_and_dividend_mismatches(self):
  for change in ({"template":2},{"factory":A},{"vault":A},{"dividend":10000},{"blockHashByte":"22"}):
   with self.subTest(change=change),patch("flyterm.launch_status._rpc",self.fixture(**change)):self.assertFalse(live_status(instance=CFG)["ok"])
 def test_wrong_chain_and_stale_chain_rejected(self):
  for change in ({"chain":"0x1"},{"age":500}):
   with patch("flyterm.launch_status._rpc",self.fixture(**change)),self.assertRaises(ValueError):live_status(instance=CFG)
 def test_graduation_is_status_not_failure(self):
  with patch("flyterm.launch_status._rpc",self.fixture(pair=F)):out=live_status(instance=CFG)
  self.assertTrue(out["ok"]);self.assertTrue(out["graduated"])
 def test_errors_never_return_config_or_credentials(self):
  _CACHE.clear()
  with patch("flyterm.launch_status.load_instance",return_value=CFG),patch("flyterm.launch_status.live_status",side_effect=ValueError("private-rpc-token")):
   out=public_status()
  self.assertFalse(out["ok"]);self.assertEqual(out["checks"],{});self.assertNotIn("private-rpc",json.dumps(out))
