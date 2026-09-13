"""Encode local-fixture hops. Live OKX aggregator calldata is not wired and must not be invented."""
from .codec import calldata,address
def quote_to_usd0(min_usd0):
    return calldata("hopQuoteToUsd0(uint256)",["uint256"],[int(min_usd0)])
def usd0_to_quote(min_quote):
    return calldata("hopUsd0ToQuote(uint256)",["uint256"],[int(min_quote)])
def live_okx_call(_route):
    raise ValueError("Live OKX hop calldata is not wired; do not arm conversion on mainnet")
def uses_googl_quote(protocol):
    quote=address(protocol.get("quote") or protocol.get("wgooglx") or protocol.get("usd0"))
    usd0=address(protocol["usd0"])
    return quote!=usd0
