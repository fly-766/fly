"""Executable notation for the BSC controller's non-neural admissibility rules.
Reference arithmetic; live fixed-point rounding is specified by PositionMathV05.sol.
"""
from decimal import Decimal as D

def target_notional(equity,leverage=10,reserve=D('0.5')):
    if leverage!=10 or not D('0.5')<=reserve<=D('0.9'):raise ValueError('Unsupported policy')
    return max(D(0),D(equity)*leverage*(1-reserve))

def additional_notional(equity,existing_notional):
    return max(D(0),target_notional(equity)-abs(D(existing_notional)))

def feedback(settled_net,booked_cost,previous_anchor):
    current=D(settled_net)-D(booked_cost);delta=current-D(previous_anchor)
    return ('reward' if delta>=D('0.01') else 'aversive' if delta<=D('-0.01') else 'none'),current

def eligible_profit(net,allocated,operating_cost,equity,basis,*,flat,settled,consistent):
    if not(flat and settled and consistent):return D(0)
    return max(D(0),min(D(net)-D(allocated)-D(operating_cost),D(equity)-D(basis)-D(operating_cost)))
