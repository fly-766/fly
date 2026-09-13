# Fly frontend integration contract — v0.4.3

The designer owns the visual frontend. This release supplies the backend contract and a minimal verification reference page; it does not replace the designer's layout.

## HTTP surface

All routes below are GET-only, same-origin, JSON and require no wallet signature. Proxy `/api/` to the loopback viewer. Keep RPC credentials on the server. Never call the transaction executor from a browser.

| Endpoint | Purpose | Unconfigured / unavailable behavior |
|---|---|---|
| `/api/verification` | Chain, creation event, registry, vault binding, creator, quote and tax checks | `published:false` before launch; `live:false` and empty `checks` on read failure |
| `/api/run` (alias `/api/state`) | Model identity, records and current brain state | Respect `ok`; absence is not a zero-valued live result |
| `/api/manifest` | Run source/data/policy fingerprints | 404 without a configured run |
| `/api/records?limit=20` | Up to 100 published neural records | 404 without a run; invalid limit is rejected |
| `/api/artifacts/<digest>` | Immutable published inputs/checkpoints referenced by records | 404 for unknown artifacts |
| `/api/operations` | Public treasury, position, accounting and transaction projection | `ok:false`, `liveEnabled:false` when not configured |
| `/api/health` | Viewer availability and operational snapshot freshness | `operationsFresh:false` after 90 seconds or without a snapshot |
| `/api/market` | Cached market feed | 503 on unavailable market data; no invented price |

Verification schema: `fly-verification/v1`. `observedAt` is Unix milliseconds. Check values are booleans from current on-chain data. Never substitute a configuration value for a passing check. `officialProduct` is a configured role, not a proof; also require `ok`, `live`, the expected CA and a fresh timestamp. Graduation is a status, not a failed identity check.

`creatorTaxOwedWei` is the System Vault's `creatorOwed()`. `managerCreatorFeesWei` is the separate Manager fee bucket. Both are raw quote-token units; wGOOGLx uses 18 decimals. Hyper/USDC amounts ending in `E6` use 6 decimals. Never label a raw quote quantity as USDC.

## Interface behavior

* Before the official launch: explain the mechanism and display an unpublished state. Do not load trial addresses as a fallback.
* Show live / paused / stale / unavailable separately. An old profitable record is not a current live result.
* Link actual transaction hashes to the correct chain. A submitted hash is not a confirmed fill.
* Keep the risk explanation: the brain computes off chain; public replay and anchored hashes are not zero-knowledge computation proofs or guaranteed returns.
* Separate principal, realized profit, bridge/operating fees and buyback inventory. No holder redemption or dividend is implied.
* The reference `/verify.html` is intentionally plain. Replace its layout when the designer delivers; retain these API semantics.

## Acceptance when the frontend arrives

Verify desktop/mobile rendering, loading/empty/error/stale states, same-origin API routing, no browser RPC secrets, correct amount units, correct mainnet links, official CA binding, and no trial records displayed as production. Preserve the pixel fly and use the approved wallet component only where a real wallet interaction is required.
