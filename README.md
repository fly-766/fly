# Fly

A fruit fly sits at a desk and watches Bitcoin.

That is the whole premise, taken seriously. Fly uses a publicly specified *Drosophila* connectome — 166,700 neurons, 25 million retained edges — as a trading controller. Market candles are encoded as light. The circuit proposes BUY, SELL, or HOLD. A contract envelope, not the fly, decides whether money may move.

Tax taken on X Layer is principal. It is meant to become Hyperliquid BTC inventory. Only realized profit is meant to come home and buy the token back. The fly does not get to invent a withdrawal.

This repository is the explanation and the source. The public site, the production deployment, and the official token are published separately, when they exist.

## How the money is supposed to move

Someone trades the token on X Layer. One percent on the buy, one percent on the sell, quoted in wrapped Google stock (wGOOGLx). That tax is not a holder dividend. It is claimed, converted toward native USDC, and bridged with Circle’s CCTP onto HyperEVM.

There it is treated as cost basis: BTC perpetual, long or flat, no more than 1×, no more than a small fixed order. The connectome may propose. Policy may veto. A fill is confirmed as a fill, not as a signature that “should have” filled.

If the book is actually ahead of principal, that surplus — and only that surplus — is allowed to return, hop back into wGOOGLx, and repurchase under caps. Pre-graduation inventory stays in a fixed contract. After graduation it can be sent to a dead address. Principal is not profit. Profit is not a holder redeem right.

```text
trade tax (wGOOGLx)
    → claim
    → convert to USDC
    → CCTP onto HyperEVM
    → BTC principal (long / flat)
    → realized profit only
    → buyback
```

## What the fly actually is

The controller is [Stonkfly](https://github.com/nftechie/stonkfly)’s MaleCNS graph, not a toy network and not a language model picking trades. Closed candles become left/right brightness. Spikes propagate. A fixed decoder emits a side. Learning, when enabled, is an engineered dopamine-like update — not a claim that the animal understands a market, and not a forecast of return.

Same input, same source, same policy should replay to the same record on the same machine. A hash of that record can later be anchored so a file cannot be quietly rewritten. That is not a zero-knowledge proof that the neuron step ran, and it is not a live track record.

## What this source contains

| Path | Role |
|---|---|
| `contracts/` | Conversion, bridge ingress, trading account, recovery, buyback |
| `flyterm/` | Connectome runtime, journals, unarmed operator planning |
| `web/` | Laboratory interface |
| `vendor/stonkfly/` | Upstream controller (MIT), without the bulk data arrays |
| `DISCLOSURE.md` | Affiliations, risk, and what is not being claimed |

Keys never live in this tree. Generated keepers stay unarmed until a deployment is configured elsewhere.

## What Fly is not

Not Google. Not IGNIX. Not Circle. Not Hyperliquid. Not Janelia. wGOOGLx is a wrapped stock token on X Layer; it is not listed GOOGL. Caps limit loss; they do not produce return. Nothing here is an offer to buy or sell a security.

## License

MIT for project source. Stonkfly remains MIT. MaleCNS data stays under its upstream terms. See [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
