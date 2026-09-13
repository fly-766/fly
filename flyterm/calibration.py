"""Mechanical acceptance is bound to the exact model; it is not a profitability score."""
import json
from .records import digest,file_digest
def verify(path,identity,expected_hash):
    if file_digest(path)!=expected_hash:raise ValueError("Calibration report fingerprint changed")
    report=json.loads(path.read_text())
    if not report.get("accepted") or report.get("modelSourceHash")!=digest(identity["source"]):raise ValueError("Calibration/model source mismatch")
    arm=report["reports"]["learning" if identity["learning"] else "frozen"]
    if arm["model"]!=identity or not arm["accepted"]:raise ValueError("Calibration identity mismatch")
    return report
def runtime_manifest(root):
    paths=["market.py","flyterm/worker.py","flyterm/account.py","flyterm/records.py","flyterm/calibration.py"]
    return {rel:file_digest(root/rel) for rel in paths}
