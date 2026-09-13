#!/usr/bin/env python3
"""Recompute the saved calibration stimuli; no market request or financial operation."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flyterm.neural import FullBrain,read_frame,output_fingerprint
from flyterm.records import file_digest
p=argparse.ArgumentParser();p.add_argument("directory",type=Path);args=p.parse_args()
report=json.loads((args.directory/"report.json").read_text())
genesis=args.directory/"genesis.npz"
if file_digest(genesis)!=report["genesisSha256"]:raise SystemExit("Genesis checksum mismatch")
brain=FullBrain(learning=False)
count=0
for name,arm in report["arms"].items():
    image=args.directory/(name+".png")
    if file_digest(image)!=arm["inputSha256"]:raise SystemExit("Input checksum mismatch")
    brain.restore(genesis);frame=read_frame(image)
    for row in arm["first"]:
        actual=brain.observe(frame,"none")
        if output_fingerprint(actual)!=row["fingerprint"]:raise SystemExit("Mismatch: "+name)
        count+=1
    print(name+": matched",flush=True)
print(json.dumps({"verified":True,"recomputedWindows":count,"source":"saved calibration inputs","networkWrites":False}))
