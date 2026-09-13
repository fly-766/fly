import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyterm.neural import FullBrain,market_frame,output_fingerprint
from flyterm.records import atomic,canonical
root=Path(__file__).resolve().parents[1]/"runs/calibration-v03"
checked={}
for mode in ["frozen","learning"]:
    brain=FullBrain(learning=mode=="learning");brain.restore(root/(mode+"-genesis.npz"))
    rows=json.loads((root/(mode+"-rows.json")).read_text())
    for row in rows:
        frame=market_frame(row["market"],"movement")
        if hashlib.sha256(frame.tobytes()).hexdigest()!=row["inputPixelHash"]:raise ValueError("Input differs")
        if output_fingerprint(brain.observe(frame,"none"))!=row["fingerprint"]:raise ValueError("Output differs")
    checked[mode]=len(rows);print(mode,len(rows),"exact",flush=True)
atomic(root/"replay.json",canonical({"verified":True,"rounds":checked,"crossMachineVerified":False}))
