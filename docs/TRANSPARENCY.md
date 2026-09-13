# Transparency

The design goal is open computation, public replay, and tight money rules — not “fully on-chain” or “trustless.”

| Stage | What is constrained | What still requires trust |
|---|---|---|
| Connectome | Full retained graph and upstream decoder; code/data/state fingerprints | Biological model and sensory encoding are approximations |
| Sensation | Public candles mapped to left/right brightness | Hand-chosen windows; public market data |
| Learning | Checkpoints and outcomes replayable in the same environment | Same-machine replay is not a cross-CPU proof and not an edge |
| Records | Sequential hashes; optional on-chain roots | A single model signer can delay, halt, or omit a proposal |
| Custody | Funds held in contracts with fixed recipients | Contract correctness, stablecoin issuers, gas |
| Orders | BTC, long/flat, size and leverage caps, reduce-only exit | Venue fills and the settlement signer |
| Principal vs profit | Tax is treated as cost basis; profit cannot be paid from principal | Funding and operating costs must still be booked |
| Bridge | Fixed asset, domains, messenger, recipient | Circle attestation; two chains |
| Buyback | Fixed token and caps | Price reference and MEV |
| Recovery | Fixed beneficiary; v0.4 deployments have no extra wait | An admin can pause and start recovery; holders have no redeem right |

A hash on chain is not a proof of correct neural execution. A settlement signature is not a zero-knowledge proof of a fill. IGNIX creator extras still accrue to an EOA and must be claimed.

Mechanical response tests and same-environment replay have passed. Shadow samples are not a statistical backtest and are not a claim of outperformance.
