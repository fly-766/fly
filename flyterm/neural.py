"""Unmodified upstream full-connectome model, with explicit source/state fingerprints."""
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from PIL import Image
from .records import canonical, file_digest, digest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"vendor/stonkfly"))
os.environ.setdefault("STONKFLY_DATA",str(ROOT/".data"))
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")

def source_manifest():
    paths=[p for p in (ROOT/"vendor/stonkfly/stonkfly").rglob("*") if p.is_file() and p.suffix in (".py",".json",".cpp")]
    paths += [Path(__file__),ROOT/"flyterm/sensory.py"]
    return {str(p.relative_to(ROOT)):file_digest(p) for p in sorted(set(paths))}

def output_fingerprint(output):
    return digest({k:v for k,v in output.items() if k!="compute_seconds"})

def frame_png(frame):
    stream=io.BytesIO()
    Image.fromarray(frame).save(stream,format="PNG")
    return stream.getvalue()

def read_frame(path):
    import numpy as np
    with Image.open(path) as im:return np.asarray(im.convert("RGB"),dtype=np.uint8).copy()

class FullBrain:
    def __init__(self,learning=True,verify=True):
        from stonkfly.data import verify as verify_data
        from stonkfly.config import Settings
        from stonkfly.neural.controller import FlyController
        self.dataset=verify_data() if verify else None
        self.controller=FlyController(Settings(learning=learning,neural_ms=500))
        self.learning=learning

    def observe(self,frame,reinforcement="none"):
        out=self.controller.observe(frame,reinforcement)
        return out|{"brain":"stonkfly-malecns","connectome":True}

    def state_fingerprint(self):
        b=self.controller.brain
        h=hashlib.sha256()
        h.update(canonical({"cursor":b.cursor,"sim_tenths_ms":int(round(float(b.sim_ms)*10)),"total_spikes":b.total_spikes,"weights_frozen":b.weights_frozen}))
        for name in sorted(set(b.fields+["weight"])):
            a=getattr(b,name)
            h.update(canonical({"name":name,"dtype":str(a.dtype),"shape":list(a.shape)}))
            h.update(a.tobytes())
        return h.hexdigest()

    def checkpoint(self,path):self.controller.save(path)
    def restore(self,path):self.controller.restore(path)

    def identity(self):
        b=self.controller.brain
        return {"dataset":self.dataset,"model":b.memory()["model"],"learning":self.learning,
                "source":source_manifest(),"build":b.build,"configuration":b.configuration_signature(),
                "neural_ms":500,"decoder":"upstream-fixed-DNp20-2Hz"}

def market_frame(market,variant="contrast"):
    import numpy as np
    from PIL import ImageDraw
    if variant=="movement":
        from .sensory import movement_frame
        return movement_frame(market)
    values=np.asarray([c["close"] for c in market["candles"][-100:]],dtype=float)
    if len(values)<2 or not np.isfinite(values).all():raise ValueError("Missing finite observations")
    if variant=="upstream":
        from stonkfly.display import market_frame as draw
        return draw("BTC-USDC",values,market["bid"],market["ask"])
    if variant!="contrast":raise ValueError("Unknown visual adapter")
    # A disclosed input adapter: remove text, colored latest-price markers and chart furniture.
    # It never observes the position, profit, decoded direction, or future price.
    im=Image.new("RGB",(320,180),(128,128,128));d=ImageDraw.Draw(im)
    span=max(float(np.ptp(values)),float(values.mean())*.002)
    center=(float(values.max())+float(values.min()))/2
    points=[(16+i*287/(len(values)-1),90-(float(v)-center)/span*116) for i,v in enumerate(values)]
    d.line(points,fill=(225,225,225),width=3)
    return np.asarray(im,dtype=np.uint8)
