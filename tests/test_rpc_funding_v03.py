import unittest,tempfile
from pathlib import Path
from flyterm.ops.rpc import Rpc,RpcError
from flyterm.ops.funding import next_funding
from flyterm.ops.venue import Venue,EvidenceIncomplete
from flyterm.ops.journal import OperationJournal
A="0x"+"11"*20
class BatchTests(unittest.TestCase):
    def test_batch_reorders_and_fails_on_missing_response(self):
        rpc=Rpc("http://127.0.0.1",31337);rpc._request=lambda q:[{"id":2,"result":"second"},{"id":1,"result":"first"}]
        self.assertEqual(rpc.batch([("eth_call",[]),("eth_call",[])]),["first","second"])
        rpc._request=lambda q:[{"id":1,"result":"first"}]
        with self.assertRaises(RpcError):rpc.batch([("eth_call",[]),("eth_call",[])])
    def test_batch_never_broadcasts(self):
        rpc=Rpc("http://127.0.0.1",31337)
        with self.assertRaises(RpcError):rpc.batch([("eth_sendRawTransaction",["0x00"])])
    def test_batch_errors_do_not_leak_provider_content(self):
        rpc=Rpc("http://127.0.0.1",31337);rpc._request=lambda q:[{"id":1,"error":{"message":"private provider details"}}]
        with self.assertRaisesRegex(RpcError,"^RPC batch call failed$"):rpc.batch([("eth_call",[])])
class FundingTests(unittest.TestCase):
    def setUp(self):
        self.cfg={"chainId":31337,"addresses":{"account":A,"reader":A},"fundingFromMs":1000}
        class Snap:
            timestamp=100000
            def get(self,*args):return False
            def core(self,*args):return {"coreBlock":20}
        self.snap=Snap()
    def event(self,time=2000):return {"time":time,"hash":"0x"+"12"*32,"delta":{"type":"funding","coin":"BTC","usdc":"-0.012345","szi":"0.001","fundingRate":"0.01"}}
    def test_funding_is_negative_cost_and_stable_event_id(self):
        venue=Venue(transport=lambda q:[self.event()])
        one=next_funding(self.snap,self.cfg,venue);two=next_funding(self.snap,self.cfg,venue)
        self.assertEqual(one["values"]["delta"],-12345);self.assertEqual(one["values"]["id"],two["values"]["id"])
    def test_recorded_event_skipped_and_cursor_persisted(self):
        self.snap.get=lambda *args:True
        with tempfile.TemporaryDirectory() as tmp:
            j=OperationJournal(Path(tmp)/"ops.sqlite")
            self.assertIsNone(next_funding(self.snap,self.cfg,Venue(transport=lambda q:[self.event()]),j))
            self.assertEqual(j.db.execute("SELECT at FROM funding_cursor").fetchone()[0],2000);j.close()
    def test_future_funding_rejected(self):
        with self.assertRaises(EvidenceIncomplete):next_funding(self.snap,self.cfg,Venue(transport=lambda q:[self.event(100000001)]))
    def test_full_recorded_page_advances_to_unrecorded_funding(self):
        pages=[]
        def transport(q):
            pages.append(q["startTime"])
            if len(pages)==1:return [self.event(2000+i) for i in range(500)]
            return [self.event(2500)]
        # 500 accounted events; then one new event.
        calls=[0]
        def get(*args):calls[0]+=1;return calls[0]<=500
        self.snap.get=get
        out=next_funding(self.snap,self.cfg,Venue(transport=transport))
        self.assertEqual(out["evidence"]["event"]["time"],2500);self.assertEqual(pages,[1000,2499])
