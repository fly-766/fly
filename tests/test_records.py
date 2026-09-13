import tempfile
import unittest
import sqlite3
from pathlib import Path
from flyterm.records import Journal,digest

class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.j=Journal(self.tmp.name)
        genesis=self.j.artifact(b"frozen model state",".npz")
        self.j.initialize({"runId":"test","genesis":genesis})
    def tearDown(self):self.j.close();self.tmp.cleanup()
    def row(self,n):
        a=self.j.artifact(b"input "+str(n).encode(),".png")
        return {"sequence":n,"runId":"test","input":a,"neural":{"side":"HOLD"}}
    def test_sequence_and_hash_tampering_detected(self):
        self.j.append(self.row(1));head=self.j.append(self.row(2))["root"]
        self.assertEqual(self.j.audit(head)["rounds"],2)
        with self.j.db:self.j.db.execute("UPDATE rounds SET body=replace(body,'HOLD','BUY') WHERE seq=1")
        with self.assertRaisesRegex(ValueError,"History changed"):self.j.audit()
    def test_asset_tampering_detected(self):
        b=self.row(1);self.j.append(b);self.j.artifact_path(b["input"]["name"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"Artifact changed"):self.j.audit()
    def test_wrong_sequence_and_run_rejected(self):
        with self.assertRaises(ValueError):self.j.append(self.row(2))
        b=self.row(1);b["runId"]="another"
        with self.assertRaises(ValueError):self.j.append(b)
    def test_artifact_paths_cannot_escape(self):
        for x in ["../policy.json","/etc/passwd","a"*64+".sec"]:
            with self.assertRaises(ValueError):self.j.artifact_path(x)
    def test_external_head_detects_truncation(self):
        self.j.append(self.row(1));head=self.j.append(self.row(2))["root"]
        with self.j.db:self.j.db.execute("DELETE FROM rounds WHERE seq=2")
        with self.assertRaisesRegex(ValueError,"externally"):self.j.audit(head)
