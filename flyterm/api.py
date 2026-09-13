"""Read-only public views of this run; no wallet keys, arbitrary paths or mutations."""
import json
import fcntl
from pathlib import Path
from .records import Journal,digest

def status(directory):
    directory=Path(directory)
    if not (directory/"journal.sqlite").exists():return {"ok":False,"state":"not_started","executionEnabled":False}
    journal=Journal(directory,readonly=True)
    try:
        manifest=journal.meta("manifest")
        rows=journal.rows(100)
        last=rows[-1] if rows else None
        count=journal.db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
        running=False
        try:
            with (directory/"worker.lock").open("rb") as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
                except BlockingIOError:running=True
        except FileNotFoundError:pass
        replay=None
        if (directory/"replay.json").exists():
            replay=json.loads((directory/"replay.json").read_text())
            if replay.get("runId")!=manifest["runId"]:replay=None
        counts={s:0 for s in ("BUY","SELL","HOLD")}
        for row in journal.db.execute("SELECT body FROM rounds"):
            side=json.loads(row[0]).get("neural",{}).get("side")
            if side in counts:counts[side]+=1
        return {"ok":True,"runId":manifest["runId"],"state":"running" if running else "recorded",
                "mode":manifest.get("mode","shadow"),"marketMode":manifest.get("marketMode","live-public"),"executionEnabled":False,"rounds":count,"sides":counts,
                "latest":last,"head":last["root"] if last else digest(manifest),
                "model":manifest["model"]["dataset"],"policy":manifest["policy"],"replay":replay,
                "onchainAnchored":False,"computationProof":"none","attestation":"public-replay"}
    finally:journal.close()

def calibration(directory):
    v3=Path(directory)/"acceptance.json"
    if v3.exists():
        report=json.loads(v3.read_text());proof=Path(directory)/"replay.json"
        return {"ok":True,"mechanicalAccepted":report["accepted"],"reports":{k:{"counts":v["counts"],"accepted":v["accepted"]} for k,v in report["reports"].items()},
                "modelSourceHash":report["modelSourceHash"],"protocol":report["protocol"],"replay":json.loads(proof.read_text()) if proof.exists() else None,
                "profitabilityProven":False}
    path=Path(directory)/"report.json"
    if not path.exists():return {"ok":False}
    report=json.loads(path.read_text())
    return {"ok":True,"repeatabilityPassed":report["repeatabilityPassed"],
            "strategyCalibrationAccepted":report["strategyCalibrationAccepted"],
            "learningFrozen":report["learningFrozen"],
            "arms":{name:{"repeatMatched":v["replayMatched"],
                         "sides":[x["output"]["side"] for x in v["first"]],
                         "differenceHz":[x["output"]["difference_hz"] for x in v["first"]]}
                    for name,v in report["arms"].items()}}
