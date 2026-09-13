"""Official Coinbase Advanced SDK execution, wrapped by an AgentKit provider.

Live execution uses price-bounded fill-or-kill spot orders. Intent is persisted
before the request. An ambiguous result is never retried as a new order.
"""

import os
import time
from datetime import datetime, timezone

from .config import D
from .market import unwrap
from .risk import Veto

TERMINAL = {"FILLED", "CANCELLED", "EXPIRED", "FAILED", "REJECTED"}


class UnresolvedOrder(RuntimeError):
    pass


class PaperBroker:
    mode = "paper"

    def __init__(self, settings, ledger):
        self.s = settings
        self.l = ledger

    def preflight(self):
        return {"mode": "paper", "network_execution": False}

    def verify_balances(self):
        pass

    def reconcile(self):
        # Paper requests never leave the process; the immutable plan contains
        # the execution quote, so an interrupted fill can settle exactly once.
        for row in self.l.pending():
            self._fill(row["plan"])

    def execute(self, plan, before_submit):
        try:
            before_submit(plan)
        except Exception:
            self.l.mark(plan["client_order_id"], "REJECTED")
            raise
        return self._fill(plan)

    def _fill(self, p):
        size = D(p["base_size"])
        price = D(p["observed_ask"] if p["side"] == "BUY" else p["observed_bid"])
        value = size * price
        fee = value * D(self.s.paper_fee)
        self.l.settle(p["client_order_id"], size, value, fee)
        return {
            "mode": "paper",
            "status": "FILLED",
            "base": str(size),
            "quote": str(value),
            "fee": str(fee),
        }


class CoinbaseBroker:
    mode = "live"

    def __init__(self, settings, ledger, client, portfolio):
        if not portfolio:
            raise ValueError("Dedicated Coinbase portfolio UUID required")
        self.s = settings
        self.l = ledger
        self.client = client
        self.portfolio = portfolio

    @classmethod
    def from_env(cls, settings, ledger):
        if os.environ.get("STONKFLY_LIVE") != "I_ACCEPT_REAL_TRADES":
            raise RuntimeError("Live opt-in missing")
        from coinbase.rest import RESTClient

        key = os.environ.get("COINBASE_KEY_FILE")
        portfolio = os.environ.get("COINBASE_PORTFOLIO_ID")
        if not key or not portfolio:
            raise RuntimeError(
                "Set COINBASE_KEY_FILE and COINBASE_PORTFOLIO_ID locally"
            )
        return cls(
            settings,
            ledger,
            RESTClient(api_key=None, api_secret=None, key_file=key, timeout=10),
            portfolio,
        )

    def accounts(self):
        result = {}
        cursor = None
        seen = set()
        while True:
            d = unwrap(
                self.client.get_accounts(
                    limit=250, cursor=cursor, retail_portfolio_id=self.portfolio
                )
            )
            for a in d.get("accounts", []):
                if a.get("retail_portfolio_id") != self.portfolio:
                    raise RuntimeError("Account portfolio mismatch")
                currency = a["currency"]
                available = D(a["available_balance"]["value"])
                hold = D(a["hold"]["value"])
                if min(available, hold) < 0 or hold:
                    raise RuntimeError("Negative or reserved external account balance")
                result[currency] = result.get(currency, D(0)) + available
            if not d.get("has_next"):
                break
            cursor = d.get("cursor")
            if not cursor or cursor in seen:
                raise RuntimeError("Invalid account pagination")
            seen.add(cursor)
        return result

    def preflight(self):
        permissions = unwrap(self.client.get_api_key_permissions())
        if (
            permissions.get("can_view") is not True
            or permissions.get("can_trade") is not True
            or permissions.get("can_transfer") is not False
        ):
            raise RuntimeError(
                "Require View + Trade, with Transfer explicitly disabled"
            )
        if permissions.get("portfolio_uuid") != self.portfolio:
            raise RuntimeError("API key is not scoped to the configured portfolio")
        self.reconcile()
        balances = self.accounts()
        if not self.l.get("live_initialized"):
            if (
                self.l.get("tick")
                or self.l.db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            ):
                raise RuntimeError("Uninitialized live ledger already has activity")
            if any(v for k, v in balances.items() if k != "USDC"):
                raise RuntimeError("Start with only USDC in a dedicated portfolio")
            cash = balances.get("USDC", D(0))
            if not 0 < cash <= D(self.s.capital):
                raise RuntimeError(
                    "Fund dedicated portfolio with 0 < USDC <= configured $100 cap"
                )
            with self.l.transaction():
                for k in ["cash", "initial_cash", "anchor"]:
                    self.l.put(k, str(cash))
                self.l.put("live_initialized", True)
        self.verify_balances()
        return {"mode": "live", "portfolio_scoped": True, "withdrawals_disabled": True}

    def verify_balances(self):
        actual = self.accounts()
        expected = {"USDC": self.l.cash}
        for p, amount in self.l.positions.items():
            expected[p.split("-")[0]] = amount
        for currency in set(actual) | set(expected):
            tolerance = D(".02") if currency == "USDC" else D(".00000001")
            if (
                abs(actual.get(currency, D(0)) - expected.get(currency, D(0)))
                > tolerance
            ):
                raise RuntimeError(
                    "External balance change; stop and reconcile rather than treat deposits as profit"
                )
        open_orders = unwrap(
            self.client.list_orders(
                order_status=["OPEN"], retail_portfolio_id=self.portfolio, limit=1
            )
        )
        if open_orders.get("orders"):
            raise RuntimeError("External/open order in dedicated portfolio")

    def execute(self, p, before_submit):
        cid = p["client_order_id"]
        side = p["side"]
        common = {
            "product_id": p["product"],
            "base_size": p["base_size"],
            "limit_price": p["limit_price"],
            "retail_portfolio_id": self.portfolio,
        }
        try:
            preview = unwrap(self.client.preview_limit_order_fok(side=side, **common))
            if preview.get("errs") or preview.get("warning"):
                raise Veto("Coinbase preview rejected or warned")
            if "commission_total" not in preview:
                raise Veto("Preview did not include fees")
            fee = D(preview["commission_total"])
            if fee < 0 or fee > D(p["fee_ceiling"]):
                raise Veto("Fee ceiling exceeded")
            if time.time() - p["quote_timestamp"] > self.s.max_quote_age:
                raise Veto("Quote expired during preview")
            self.verify_balances()
            before_submit(p)
        except Exception:
            self.l.mark(cid, "REJECTED")
            raise
        # This durable transition precedes any request that can place an order.
        self.l.mark(cid, "UNKNOWN")
        try:
            r = unwrap(
                self.client.limit_order_fok(client_order_id=cid, side=side, **common)
            )
        except Exception as e:
            raise UnresolvedOrder(
                "Submission outcome unknown; reconcile before any further trade"
            ) from e
        if r.get("success") is False:
            self.l.mark(cid, "REJECTED")
            return {"status": "REJECTED", "mode": "live"}
        oid = r.get("success_response", {}).get("order_id")
        if r.get("success") is not True or not oid:
            raise UnresolvedOrder("Exchange response lacks an unambiguous order ID")
        self.l.mark(cid, "ACCEPTED", oid)
        deadline = time.monotonic() + 30
        while True:
            if self._settle(cid, oid, p):
                return {"mode": "live", "status": "SETTLED", "client_order_id": cid}
            if time.monotonic() >= deadline:
                break
            time.sleep(1)
        # FOK should be terminal. Do not assume that a timeout implies no fill.
        raise UnresolvedOrder("Order is not terminal; live execution stopped")

    def _settle(self, cid, oid, p):
        r = unwrap(self.client.get_order(oid)).get("order", {})
        if (
            r.get("order_id") != oid
            or r.get("client_order_id") != cid
            or r.get("product_id") != p["product"]
            or r.get("side") != p["side"]
        ):
            raise UnresolvedOrder("Order identity mismatch")
        if r.get("status") not in TERMINAL:
            return False
        for key in ["filled_size", "filled_value", "total_fees"]:
            if key not in r:
                raise UnresolvedOrder("Final order lacks fill/fee accounting")
        self.l.settle(cid, r["filled_size"], r["filled_value"], r["total_fees"])
        return True

    def reconcile(self):
        for row in self.l.pending():
            cid = row["id"]
            p = row["plan"]
            oid = row["exchange_id"]
            if row["status"] == "PREPARED":
                # Network submission cannot have happened before UNKNOWN.
                self.l.mark(cid, "REJECTED")
                continue
            if not oid:
                cursor = None
                seen = set()
                found = []
                while True:
                    r = unwrap(
                        self.client.list_orders(
                            start_date=datetime.fromtimestamp(
                                row["created"] - 60, timezone.utc
                            ).isoformat(),
                            retail_portfolio_id=self.portfolio,
                            cursor=cursor,
                            limit=100,
                        )
                    )
                    found += [
                        o
                        for o in r.get("orders", [])
                        if o.get("client_order_id") == cid
                    ]
                    if not r.get("has_next"):
                        break
                    cursor = r.get("cursor")
                    if not cursor or cursor in seen:
                        raise UnresolvedOrder("Order pagination failed")
                    seen.add(cursor)
                if len(found) != 1:
                    raise UnresolvedOrder(
                        "Uncertain submission not uniquely found. Check Coinbase; no automatic resubmission."
                    )
                oid = found[0]["order_id"]
                self.l.mark(cid, "ACCEPTED", oid)
            if not self._settle(cid, oid, p):
                raise UnresolvedOrder("Order still pending at Coinbase")
