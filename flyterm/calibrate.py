"""Paired controls. No weights or decoder thresholds are fitted to produce a trade."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from market import fetch_market
from .neural import FullBrain, frame_png, market_frame, output_fingerprint
from .records import canonical,atomic,file_digest

ROOT=Path(__file__).resolve().parents[1]

def calibrate(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    brain=FullBrain(learning=False)
    market=fetch_market()
    genesis=directory/"genesis.npz";brain.checkpoint(genesis)
    upstream=market_frame(market,"upstream")
    contrast=market_frame(market,"contrast")
    stimuli={"neutral_gray":np.full((180,320,3),128,dtype=np.uint8),
             "upstream":upstream,"upstream_mirror":np.ascontiguousarray(upstream[:,::-1]),
             "contrast":contrast,"contrast_mirror":np.ascontiguousarray(contrast[:,::-1]),
             "bright_left":np.concatenate([np.full((180,160,3),235,dtype=np.uint8),np.zeros((180,160,3),dtype=np.uint8)],axis=1),
             "bright_right":np.concatenate([np.zeros((180,160,3),dtype=np.uint8),np.full((180,160,3),235,dtype=np.uint8)],axis=1)}
    results={}
    for name,frame in stimuli.items():
        atomic(directory/(name+".png"),frame_png(frame))
        arms=[]
        for repeat in range(2):
            brain.restore(genesis)
            windows=[]
            for window in range(4):
                output=brain.observe(frame,"none")
                windows.append({"window":window,"output":output,"fingerprint":output_fingerprint(output)})
            arms.append(windows)
        same=[x["fingerprint"] for x in arms[0]]==[x["fingerprint"] for x in arms[1]]
        results[name]={"replayMatched":same,"inputSha256":file_digest(directory/(name+".png")),"first":arms[0],"repeat":arms[1]}
        print(json.dumps({"stimulus":name,"repeatMatched":same,"sides":[x["output"]["side"] for x in arms[0]],
                          "differenceHz":[x["output"]["difference_hz"] for x in arms[0]]}),flush=True)
    result={"schema":"flyterm-calibration/v1","at":int(time.time()*1000),"model":brain.identity(),"market":market,
            "genesisSha256":file_digest(genesis),"arms":results,
            "repeatabilityPassed":all(a["replayMatched"] for a in results.values()),
            "learningFrozen":True,"decoderChanged":False,"strategyCalibrationAccepted":False,
            "executionEnabled":False,"note":"These controls test input sensitivity and repeatability, not learned profitability or release readiness."}
    atomic(directory/"report.json",canonical(result))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,default=ROOT/"runs/calibration")
    a=p.parse_args();calibrate(a.out)
