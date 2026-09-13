"""Disclosed sensory encoding. Market movement changes light, never selects an order."""
import numpy as np
PARAMETERS={"version":"movement-light-v1","completedBarsOnly":True,"horizon":3,"volatilityLookback":60,"deadbandZ":0.05,"peak":235}
def movement_frame(market):
    cutoff=int(float(market["providerTime"])*1000)
    bars=[c for c in market["candles"] if int(c["closeTime"])<=cutoff]
    if len(bars)<62:raise ValueError("Need 62 completed bars")
    prices=np.asarray([c["close"] for c in bars],dtype=np.float64)
    if not np.isfinite(prices).all() or np.any(prices<=0):raise ValueError("Invalid completed prices")
    returns=np.diff(np.log(prices))
    volatility=max(float(np.std(returns[-60:])),1e-6)
    movement=float(np.log(prices[-1]/prices[-4]))/(volatility*np.sqrt(3))
    frame=np.zeros((180,320,3),dtype=np.uint8)
    if abs(movement)<0.05:frame[:]=128
    else:
        value=int(round(235*min(abs(movement),1.0)))
        if movement>0:frame[:,160:]=value
        else:frame[:,:160]=value
    return frame
