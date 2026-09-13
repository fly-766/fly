import unittest
from types import SimpleNamespace
import numpy as np
from flyterm.neural import FullBrain

class FingerprintTests(unittest.TestCase):
    def test_derived_clock_representation_does_not_change_state(self):
        x=FullBrain.__new__(FullBrain)
        b=SimpleNamespace(cursor=0,sim_ms=0,total_spikes=0,weights_frozen=False,fields=["v"],v=np.array([1],dtype=np.float32),weight=np.array([2],dtype=np.float32))
        x.controller=SimpleNamespace(brain=b)
        h=x.state_fingerprint();b.sim_ms=0.0
        self.assertEqual(h,x.state_fingerprint())
        b.v[0]=3
        self.assertNotEqual(h,x.state_fingerprint())
