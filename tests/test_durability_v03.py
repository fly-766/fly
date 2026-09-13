import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
from flyterm.live import LiveBrain
from flyterm.errors import ObserverRestartRequired
from flyterm.ops.keeper import Keeper
class DurabilityTests(unittest.TestCase):
    def test_failed_journal_write_never_advances_model_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            live=LiveBrain.__new__(LiveBrain);live._usable=True;live.directory=Path(tmp);live.rows=[];live.manifest={"runId":"fixture"}
            count=[0]
            def observe(*args):count[0]+=1;return {"side":"BUY"}
            live.brain=NS(observe=observe,state_fingerprint=lambda:str(count[0])*64)
            def append(body):raise OSError("Simulated full disk")
            live.j=NS(artifact=lambda *args:{"name":"fixture.png"},append=append)
            market={"providerTime":4000,"candles":[{"time":i*60000,"closeTime":i*60000+59999,"close":1} for i in range(62)]}
            snapshot={"pending":0,"nativePrincipalE6":0,"unallocatedSpotE6":0,"tradingNetE6":0,"operatingCostE6":0}
            with patch("flyterm.live.market_frame",return_value=np.zeros((2,2,3),dtype=np.uint8)):
                with self.assertRaises(ObserverRestartRequired):live.observe(snapshot,market)
                with self.assertRaises(ObserverRestartRequired):live.observe(snapshot,market)
            self.assertEqual(count[0],1);self.assertEqual(live.rows,[])
    def test_keeper_exits_and_records_restart_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            k=Keeper.__new__(Keeper);k.directory=Path(tmp);k.live=False
            def step():raise ObserverRestartRequired("Must restore")
            k.step=step
            with self.assertRaises(ObserverRestartRequired):k.run(steps=1)
            self.assertIn("RESTART_REQUIRED",(Path(tmp)/"health.json").read_text())
