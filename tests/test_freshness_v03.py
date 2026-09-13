import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from flyterm.ops.keeper import Keeper
from flyterm.ops.public import publish
A="0x"+"11"*20
class FreshnessTests(unittest.TestCase):
    def check_age(self,stamp):
        k=Keeper.__new__(Keeper);k.config={"chains":{"xlayer":{"chainId":196,"signerAddress":A},"hyper":{"chainId":999,"signerAddress":A}}}
        k.live=False;k.directory=Path(".");k.j=NS(pending=lambda *args:[])
        k.rpcs={"xlayer":NS(chain_id=196),"hyper":NS(chain_id=999)}
        def snapshot(rpc):return NS(rpc=rpc,timestamp=1000 if rpc.chain_id==196 else stamp,block={"hash":"0x"+"12"*32})
        with patch("flyterm.ops.keeper.Snapshot",side_effect=snapshot),patch("flyterm.ops.public.publish"),patch("flyterm.ops.keeper.time.time",return_value=1000):
            result=k.step()
        self.assertEqual(result,{"state":"WAIT","reason":"stale_chain_snapshot","chains":["hyper"]})
    def test_stale_chain_stops_before_any_action(self):self.check_age(909)
    def test_future_chain_stops_before_any_action(self):self.check_age(1031)
    def test_public_timestamp_uses_older_chain(self):
        addresses={k:A for k in ("account","reader","registry","buyback")}
        account={"costBasisE6":500000000,"tradingNetE6":0,"operatingCostE6":0,"availableProfit":0,"core":{"equityE6":500000000},"pending":0,"paused":False}
        def snap(stamp,chain):
            return NS(timestamp=stamp,rpc=NS(chain_id=chain),tag="0x1",block={"hash":"0x"+"34"*32},account=lambda *args:account,
                      get=lambda at,sig,types,*args:b"\x01"*32 if types==["bytes32"] else 0)
        cfg={"liveEnabled":False,"chains":{"hyper":{"addresses":addresses},"xlayer":{"projectToken":A}}}
        with tempfile.TemporaryDirectory() as tmp:
            publish(Path(tmp),cfg,{"hyper":snap(900,999),"xlayer":snap(1000,196)},NS(db=NS(execute=lambda *args:[])))
            report=json.loads((Path(tmp)/"public.json").read_text())
        self.assertEqual(report["at"],900000);self.assertEqual(report["chainTimes"],{"hyper":900000,"xlayer":1000000})
