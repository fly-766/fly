# Fly v0.5 — signed positions and a 20x entry ceiling

This release adds long/flat/short execution. It is a new contract release, not an upgrade of previously deployed trial accounts. All existing token instances remain trials. Mainnet execution is not established by local acceptance.

## Position semantics

| Native position | BUY proposal | SELL proposal |
|---|---|---|
| Flat | Open long | Open short, if enabled |
| Long | No pyramiding | Reduce/close long |
| Short | Reduce/close short | No pyramiding |

A reversal first closes the held position. Another entry requires a later valid commit, a flat and settled account, and the entry cooldown. A single order cannot cross zero. Closing orders are reduce-only on either side. The guardian can disable new short entries without preventing buy-to-cover.

## Position and margin constraints

The immutable project leverage ceiling is configurable up to 20. The native BTC account's actual leverage must match the configured ceiling, and the asset must support it. The reader checks this at entry. The implementation does not invent a CoreWriter leverage-change action.

The margin model is **cross margin in a dedicated contract account**, not isolated margin. The contract only submits BTC orders and does not register an unrestricted API trading agent. Only explicitly allocated test capital should enter a trial account; unrelated existing account capital must not be used as collateral.

With equity E, maximum order notional M, configured leverage L and reserve fraction r, the entry budget is min(M, L * E * (1-r)). Quantity uses the greater of the reference price and the limit price, rounded down to the venue lot size. This prevents a short's lower sell limit from enlarging its reference-price exposure. The example limits use L=20, r=10%, M=200 USDC and a 2-USDC loss-stop trigger. With 10 USDC equity, the pre-rounding budget is therefore at most 180 USDC, not 200. These are reviewable trial defaults, not a return target or a guaranteed maximum loss.

The account reads current signed positions. Unexpected position changes without a pending known order trigger quarantine and disable new trading/profit extraction. This includes possible liquidation, ADL or unexplained account mutation. Known partial fills are settled using their actual final signed quantity. A stop condition can request emergency closure; price gaps, delayed CoreWriter actions and insufficient liquidity can produce losses beyond the trigger.

## Accounting

Order settlement binds `ORDER_V05` and a signed `int64 finalPositionE8`. The magnitude of the previous position remains separately available for proportional cost-basis retirement. Closing PnL is proceeds minus retired basis for a long and retired basis minus repurchase cost for a short. Fees remain costs in both directions. A signed final position with the wrong sign is rejected.

The v0.4 immediate recovery path is preserved. Principal and profit cannot exit while a known open position or pending operation remains. Profit eligibility requires the recorded and native positions to agree, as well as the existing flat/settled and accounting checks.

## Preparing a profile

Use a new run with `config/policy-v05.json`. Legacy `policy.json` and v03/v04 contracts remain for historical compatibility. `init-run` defaults to the v05 policy, and `prepare-deploy` defaults to account version 5. A v04 profile can be requested explicitly for archived workflows.

```
python -m flyterm.ops init-run --out runs/production-v05 --policy config/policy-v05.json
python -m flyterm.ops prepare-deploy --account-version 5 --trade-limits config/trade-limits-v05.example.json --roles <private-roles-file> --token <verified-token> --manifest <new-run-manifest> --out <deployment-plan>
```

Replace every placeholder with a separately reviewed value. The deployment plan remains unsigned. After actual deployment, use `prepare-keeper --tax-vault <verified-vault>` and verify contract versions, constructor limits, native leverage, code pins, return recipients and funds before enabling any user-operated live process.

The new reader is `NativeCoreReadV05`; the account is `TradingAccountV05`. Historical v04 deployed contracts remain long-only and cannot be converted into short-enabled accounts by changing frontend text or a JSON policy.

## Evidence scope

`contracts/test/V05LongShort.t.sol` covers short entry, cover, profit and loss signs, partial cover, independent disable-short control, same-side rejection, flat-first reversals, actual-leverage mismatch, position drift, immediate post-cover recovery and exposure bounds. Python checks cover action selection, signed ABI/payloads and deployment generation. `scripts/accept_v05_local.py` composes the tax, trading, return and buyback paths on ephemeral Anvil.

The optional full-model mode runs the unchanged connectome against saved market observations retimed to the local chain, with simulated fills and Circle attestations. Test-end cleanup is labeled separately from neural orders. It is not a mainnet performance result. Use a fresh run directory for each new source/policy version.

## Frontend fields

For v05, `/api/operations` adds `position.quantityE8` (signed decimal string), `position.side` (LONG/SHORT/FLAT), and `riskControls`: accountVersion, maxEntryLeverage, entryReserveBps, shortEnabled, maxOrderE6, lossStopE6 and marginMode. Display actual position separately from the current neural proposal. A SELL proposal may be a close, an opening short, or a rejected action depending on state. Never infer exposure from the proposal label alone.

## Protocol references

* Hyperliquid [CoreWriter and precompiles](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm/interacting-with-hypercore).
* Hyperliquid [margining](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining) and [liquidations](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations).
* Hyperliquid [funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding).
