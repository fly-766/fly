"""Fixed, public Hyperliquid information endpoints. No signer or exchange API."""
import json
import math
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def positive(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing numeric field")
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise ValueError("Invalid positive numeric field")
    return n


def normalize_candles(raw, now_ms):
    rows = {}
    for c in raw:
        try:
            if c.get("s") != "BTC" or c.get("i") != "1m":
                continue
            t, end = int(c["t"]), int(c["T"])
            o, h, low, close = [positive(c[k]) for k in ("o", "h", "l", "c")]
            v = float(c["v"])
            if not math.isfinite(v) or v < 0 or not 0 < t <= now_ms + 5000:
                continue
            if end < t or low > min(o, close) or h < max(o, close) or low > h:
                continue
            rows[t] = dict(time=t, closeTime=end, open=o, high=h, low=low,
                           close=close, volume=v)
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return [rows[t] for t in sorted(rows)][-120:]


def info(payload):
    if payload.get("type") not in {"metaAndAssetCtxs", "l2Book", "candleSnapshot"}:
        raise ValueError("Read-only info request not allowed")
    request = urllib.request.Request(
        "https://api.hyperliquid.xyz/info", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "FlyTerm-Observer/0.1"},
        method="POST")
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read(2_000_000))


def fetch_market():
    now = time.time()
    now_ms = int(now * 1000)
    requests = [{"type": "metaAndAssetCtxs"}, {"type": "l2Book", "coin": "BTC"},
                {"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1m",
                 "startTime": now_ms - 120 * 60000, "endTime": now_ms}}]
    with ThreadPoolExecutor(max_workers=3) as pool:
        meta, book, history = list(pool.map(info, requests))
    idx = next(i for i, a in enumerate(meta[0]["universe"]) if a["name"] == "BTC")
    asset, ctx = meta[0]["universe"][idx], meta[1][idx]
    if asset.get("isDelisted") or book.get("coin") != "BTC":
        raise ValueError("Unexpected market")
    bid, ask = [positive(level[0]["px"]) for level in book["levels"]]
    if ask < bid:
        raise ValueError("Crossed book")
    stamp = positive(book["time"]) / 1000
    if not -5 <= now - stamp <= 60:
        raise ValueError("Stale or future book")
    candles = normalize_candles(history, now_ms)
    if not candles or now_ms - candles[-1]["time"] > 120000:
        raise ValueError("Candle feed has not advanced")
    funding = float(ctx["funding"])
    decimals = asset["szDecimals"]
    if not math.isfinite(funding) or type(decimals) is not int or not 0 <= decimals <= 8:
        raise ValueError("Invalid market metadata")
    return {"ok": True, "source": "Hyperliquid public info", "symbol": "BTC",
            "quoteAsset": "USDC", "markPrice": positive(ctx["markPx"]),
            "previousDayPrice": positive(ctx["prevDayPx"]), "bid": bid, "ask": ask,
            "funding": funding, "sizeDecimals": decimals, "providerTime": stamp,
            "fetchedAt": time.time(), "candles": candles, "stale": False,
            "executionEnabled": False}


class MarketCache:
    def __init__(self, loader=fetch_market, clock=time.time):
        self.loader, self.clock = loader, clock
        self.value, self.attempted_at = None, -float("inf")
        self.failed = False
        self.lock = threading.Lock()

    def get(self):
        with self.lock:
            now = self.clock()
            if now - self.attempted_at >= 8:
                self.attempted_at = now
                try:
                    self.value = self.loader()
                    self.failed = False
                except Exception:
                    self.failed = True
            if self.value is None:
                return {"ok": False, "stale": True, "executionEnabled": False,
                        "error": "Hyperliquid public market is temporarily unavailable"}
            result = dict(self.value)
            result["stale"] = self.failed or now - result["providerTime"] > 30
            return result
