"""USDC-margined long/flat SHADOW ledger. No venue submission or signing."""
from decimal import Decimal, ROUND_DOWN
from collections import deque

def D(value):
    if isinstance(value,bool) or value is None: raise ValueError("Invalid amount")
    n=Decimal(str(value))
    if not n.is_finite(): raise ValueError("Non-finite amount")
    return n

def floor_size(size, decimals):
    return D(size).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_DOWN)

class ShadowAccount:
    def __init__(self, capital="500", state=None):
        self.collateral=D(capital)
        self.principal=D(capital)
        self.quantity=D(0)
        self.entry=D(0)
        self.realized=D(0)
        self.fees=D(0)
        self.funding=D(0)
        self.distributed=D(0)
        self.last_time=None
        self.last_mark=None
        self.last_funding=None
        self.halted=False
        self.order_day=0;self.orders_today=0;self.last_order_at=0
        if state:
            for k in ("collateral","principal","quantity","entry","realized","fees","funding","distributed"):
                setattr(self,k,D(state[k]))
            for k in ("last_time","last_mark","last_funding","halted","order_day","orders_today","last_order_at"): setattr(self,k,state.get(k,getattr(self,k)))

    def equity(self,mark): return self.collateral+self.quantity*(D(mark)-self.entry)
    def snapshot(self,mark):
        return {k:str(getattr(self,k)) for k in ("collateral","principal","quantity","entry","realized","fees","funding","distributed")} | {
            "equity":str(self.equity(mark)), "availableAt1x":str(max(D(0),self.equity(mark)-self.quantity*D(mark))),
            "last_time":self.last_time,"last_mark":self.last_mark,"last_funding":self.last_funding,
            "halted":self.halted,"order_day":self.order_day,"orders_today":self.orders_today,"last_order_at":self.last_order_at, "mode":"shadow", "fundingMethod":"time-proportional estimate; not venue settlement"}

    def deposit(self, amount):
        amount=D(amount)
        if amount<=0: raise ValueError("Positive deposit required")
        self.collateral+=amount
        self.principal+=amount

    def mark(self, market):
        now=int(market["providerTime"]*1000)
        if self.last_time is not None:
            elapsed=max(0,now-int(self.last_time))/1000
            # Funding is an explicitly estimated shadow cost, never a claimed real fill.
            charge=self.quantity*D(self.last_mark)*D(self.last_funding)*D(elapsed)/D(3600)
            self.collateral-=charge
            self.funding+=charge
        self.last_time=now
        self.last_mark=str(market["markPrice"])
        self.last_funding=str(market["funding"])

    def transact(self,side,size,price,fee_rate="0.00045"):
        size,price,rate=D(size),D(price),D(fee_rate)
        if side not in ("BUY","SELL") or size<=0 or price<=0 or not 0<=rate<=D(".02"): raise ValueError("Invalid execution")
        fee=size*price*rate
        if side=="BUY":
            new=self.quantity+size
            if new*price>self.equity(price)-fee: raise ValueError("One-times exposure cap")
            self.entry=(self.quantity*self.entry+size*price)/new
            self.quantity=new
        else:
            if size>self.quantity: raise ValueError("Reduce-only violation")
            pnl=size*(price-self.entry)
            self.collateral+=pnl
            self.realized+=pnl
            self.quantity-=size
            if self.quantity==0:self.entry=D(0)
        self.collateral-=fee
        self.fees+=fee
        return {"status":"SHADOW_FILLED","source":"neural","side":side,"quantity":str(size),"price":str(price),"fee":str(fee)}

    def distributable(self):
        if self.quantity!=0 or self.halted: return D(0)
        return max(D(0),min(self.collateral-self.principal,self.realized-self.fees-self.funding-self.distributed))

    def distribute(self,amount):
        amount=D(amount)
        if amount<=0 or amount>self.distributable():raise ValueError("Not realized distributable profit")
        self.collateral-=amount
        self.distributed+=amount

class ShadowGuard:
    def __init__(self, policy, sides=()):
        self.policy=policy
        self.sides=deque(sides,maxlen=policy["biasWindow"])

    def execute(self,account,neural,market,*,calibration_passed=False):
        side=neural["side"]
        self.sides.append(side)
        mark=D(market["markPrice"])
        if market.get("stale") or not market.get("ok"):return {"status":"VETO","reason":"stale_market","source":"risk"}
        if account.equity(mark)<=account.principal-D(self.policy["lossStopUsdc"]):account.halted=True
        if account.halted:
            if account.quantity:
                r=account.transact("SELL",account.quantity,D(market["bid"])*(1-D(self.policy["slippage"])),self.policy["feeRate"])
                return r|{"source":"risk","reason":"loss_stop_reduce_only"}
            return {"status":"VETO","reason":"risk_halted","source":"risk"}
        if side=="HOLD":return {"status":"HOLD","source":"neural"}
        if side=="SELL":
            if account.quantity==0:return {"status":"VETO","reason":"no_long_position","source":"risk"}
            return account.transact("SELL",account.quantity,D(market["bid"])*(1-D(self.policy["slippage"])),self.policy["feeRate"])
        if side!="BUY":raise ValueError("Unknown neural side")
        if not calibration_passed:return {"status":"VETO","reason":"calibration_not_accepted","source":"risk"}
        if len(self.sides)==self.sides.maxlen and len(set(self.sides))==1:
            return {"status":"VETO","reason":"persistent_directional_bias","source":"risk"}
        if self.policy.get("singlePosition") and account.quantity>0:return {"status":"VETO","reason":"existing_long_position","source":"risk"}
        now=int(market.get("providerTime",0));day=now//86400
        if account.order_day!=day:account.order_day=day;account.orders_today=0
        if now-account.last_order_at<self.policy.get("orderCooldownSeconds",0):return {"status":"VETO","reason":"order_cooldown","source":"risk"}
        if account.orders_today>=self.policy.get("maxOrdersPerDay",100000):return {"status":"VETO","reason":"daily_order_limit","source":"risk"}
        price=D(market["ask"])*(1+D(self.policy["slippage"]))
        room=max(D(0),account.equity(price)-account.quantity*price)
        budget=min(D(self.policy["maxOrderUsdc"]),room)/(1+D(self.policy["feeRate"]))
        size=floor_size(budget/price,market["sizeDecimals"])
        if size<=0 or size*price<D(self.policy["minimumNotionalUsdc"]):return {"status":"VETO","reason":"below_minimum_or_no_capacity","source":"risk"}
        result=account.transact("BUY",size,price,self.policy["feeRate"]);account.last_order_at=now;account.orders_today+=1
        return result
