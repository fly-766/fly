# User-executed mainnet acceptance checklist — v0.5

Status: preparation only. No mainnet orders, wallet signatures, transfers or deployments have been executed for this release. Test funds are not automatically allocated. All previously issued tokens are trials.

## Budget to review

The draft uses 10 USDC of trading principal, a 20x configured/native leverage requirement, 10% entry reserve, a 200-USDC absolute order ceiling and a 2-USDC loss-stop trigger. With that principal, the ordinary entry budget is at most approximately 180 USDC before lot rounding. If "10 USDC" instead means total notional, reduce the order ceiling to 10 USDC and re-review funding/minimum-order constraints. Activation and gas costs must be quoted separately before funding; do not assume all wallet balance is usable trading margin.

## Required before a user signs

1. Inspect the exact newly deployed v05 account, reader, registry, settlement and fixed return routes. The old immutable trial accounts cannot be reused as a 20x short account.
2. Recheck available HyperEVM USDC, Core balances, all open orders/positions, current BTC minimum size, lot/tick rules, fees, actual native leverage and asset maximum leverage. Never reuse an old balance screenshot as funding evidence.
3. Allocate only the reviewed test principal to the dedicated account. Keep old principal and unrelated collateral outside the test. Record activation/transfer costs separately.
4. Generate a fresh unsigned action using the exact profile and current chain state. Check account, side, reduce-only flag, quantity, limit, notional, deadline, gas and expected state transition before signing in the user's wallet.
5. For autonomous-model acceptance, use an actual fresh model commitment. If a direction is exercised manually, label it as a directed test; never forge a neural output to produce the desired direction.
6. Observe terminal execution and reconcile native signed quantity, cost basis and fees. A transaction hash or EVM receipt alone does not establish a filled HyperCore order.
7. To test the opposite direction, first close and confirm flat. Use a new signal/commit and respect entry cooldown; never flip through zero in one order.
8. Finish flat, settle costs, pause new entries and reconcile any remaining orders. Verify the fixed-beneficiary exit path with the actual deployed release. Preserve failed, rejected and unknown-outcome records.

An unsigned plan is not a fill, and local simulation is not mainnet acceptance. Publishing source must retain that distinction. The assistant can review public state and prepared data; the user performs financial signatures and execution.

## Unsigned Hyper-only deployment preparation

`scripts/prepare_v05_hyper_canary.py` produces six nonce-pinned deployment payloads and capped USDC approval/funding calldata. It has no RPC, key loading, signing or broadcast path. It uses the existing same-chain canary funding adapter, so this test does not establish tax collection, cross-chain CCTP or production token buyback. The three trading/exit Core accounts still require activation and separate fee review. The account caps trial order attempts at four per day. Recheck the nonce and every binding before the user executes any payload.
