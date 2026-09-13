import copy,json,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
from flyterm.ops.hop import validate_quote,validate_intent_quote,OkxQuotes,QuoteUnavailable
from flyterm.ops.codec import calldata
A,B,C,D,E=["0x"+x*40 for x in "12345"]
POLICY={"enabled":True,"router":D,"spender":E,"selectors":["0xf2c42696"],"maxAgeSeconds":30,"maxSlippageBps":100,"maxPriceImpactBps":100}
REQUEST={"source":A,"destination":B,"receiver":C,"chainId":196,"amount":"1000000000000000"}
def document():
 return {"quotedAt":100,"response":{"ok":True,"data":[{"routerResult":{"action":"ok","swapMode":"exactIn","chainIndex":"196","fromToken":{"tokenContractAddress":A},"toToken":{"tokenContractAddress":B},"fromTokenAmount":REQUEST["amount"],"toTokenAmount":"300000","priceImpactPercent":"-0.1"},"tx":{"from":C,"to":D,"data":"0xf2c42696"+"00"*32,"value":"0","minReceiveAmount":"297000","slippagePercent":"1"}}]}}
class HopQuotesTests(unittest.TestCase):
 def test_exact_input_and_minimum_use_different_decimals(self):
  q=validate_quote(document(),REQUEST,POLICY,100);self.assertEqual(q["minimum"],297000);self.assertEqual(q["amount"],REQUEST["amount"])
 def test_minimum_uses_token_integer_rounding(self):
  j=document();j["response"]["data"][0]["routerResult"]["toTokenAmount"]="300001"
  self.assertEqual(validate_quote(j,REQUEST,POLICY,100)["minimum"],297000)
 def test_expired_future_and_wrong_route_rejected(self):
  for now in [99,131]:
   with self.assertRaises(QuoteUnavailable):validate_quote(document(),REQUEST,POLICY,now)
  changes=[("routerResult","action","warn"),("routerResult","chainIndex","999"),("routerResult","swapMode","exactOut"),("routerResult","fromTokenAmount","1"),("routerResult","priceImpactPercent","NaN"),("routerResult","priceImpactPercent","2"),("tx","from",A),("tx","to",E),("tx","value","1"),("tx","data","0xdeadbeef"),("tx","minReceiveAmount","1"),("tx","slippagePercent","5")]
  for section,key,value in changes:
   j=document();j["response"]["data"][0][section][key]=value
   with self.subTest(key=key),self.assertRaises(QuoteUnavailable):validate_quote(j,REQUEST,POLICY,100)
  for side in ["fromToken","toToken"]:
   j=document();j["response"]["data"][0]["routerResult"][side]["tokenContractAddress"]=E
   with self.assertRaises(QuoteUnavailable):validate_quote(j,REQUEST,POLICY,100)
 def test_transport_only_requests_unsigned_data(self):
  seen=[]
  def run(args,**kwargs):seen.append(args);return SimpleNamespace(returncode=0,stdout=json.dumps(document()["response"]))
  cfg={"chainId":196,"okxQuotes":POLICY,"protocol":{"hopRouter":D,"hopSpender":E}}
  q=OkxQuotes(run=run,clock=lambda:100).quote(A,B,int(REQUEST["amount"]),C,cfg)
  self.assertEqual(seen[0][1:3],["swap","swap"]);self.assertNotIn("execute",seen[0]);self.assertEqual(q["minimum"],297000)
 def test_transport_error_does_not_leak_stderr(self):
  runner=lambda *a,**k:SimpleNamespace(returncode=1,stdout="secret",stderr="credential")
  cfg={"chainId":196,"okxQuotes":POLICY,"protocol":{"hopRouter":D,"hopSpender":E}}
  with self.assertRaisesRegex(QuoteUnavailable,"transport unavailable"):OkxQuotes(run=runner).quote(A,B,1,C,cfg)
 def test_signing_rechecks_expiry_and_call_binding(self):
  q=validate_quote(document(),REQUEST,POLICY,100);cfg={"okxQuotes":POLICY,"addresses":{"converter":C,"buyback":D},"protocol":{"wgooglx":A,"usd0":B}}
  intent={"to":C,"hopQuote":q,"data":calldata("convert(uint256,uint256,bytes)",["uint256","uint256","bytes"],[int(q["amount"]),q["minimum"],bytes.fromhex(q["data"][2:])])}
  with patch("flyterm.ops.hop.time.time",return_value=110):validate_intent_quote(intent,cfg)
  with patch("flyterm.ops.hop.time.time",return_value=131),self.assertRaises(QuoteUnavailable):validate_intent_quote(intent,cfg)
  bad=copy.deepcopy(intent);bad["hopQuote"]["minimum"]=1
  with patch("flyterm.ops.hop.time.time",return_value=110),self.assertRaises(QuoteUnavailable):validate_intent_quote(bad,cfg)
