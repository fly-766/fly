# Fly v0.4.3 — backend release candidate

This is local engineering acceptance, not a funded production deployment. All previously issued tokens are trial instances. The friend-provided frontend, official CA, domain and server are supplied later.

## Completed scope

* System Vault taxes use `creatorOwed()`, `sync()` and `claimCreator()`. Manager `creatorAccrued` is a separate income bucket.
* A confirmed creator-claim receipt authorizes only its actual quote-token inflow to be swept to the fixed converter. One receipt cannot fund multiple operations. Planned sweeps resume identically; uncertain or failed sweeps require reconciliation.
* The unsigned `onchainos swap swap` adapter checks chain, exact source/destination assets and input amount, fixed caller/router, zero native value, route verdict, price impact, minimum output, reviewed selector and expiry. Signing rechecks freshness and calldata binding. No `swap execute` command is used.
* Router and approval proxy are separate immutable addresses. Dynamic swap calldata is callable only by the fixed execution operator. Each allowance is cleared; exact input and minimum output are checked by on-chain balance changes. Unrelated wrapped-token dust cannot block conversion.
* Principal CCTP hooks, external fill reconciliation, profit-only returns and immediate-recovery contracts retain their existing accounting boundaries.
* The verifier checks the confirmed creation event, Manager-to-vault relation and registry `factoryOf(uint16)`, plus current tax and ownership fields. Unpublished is the default; read errors never become green checks.

## Production sequence

1. Integrate the friend's frontend using `FRONTEND-HANDOFF-v043.md`. This source is developed only in the canonical Linux checkout.
2. Prepare the server's isolated Linux checkout, Python environment, locked contract dependencies, data arrays and Linux Onchain OS CLI. Configure the CLI for unsigned DEX data; never use its wallet execution commands in this service. Set `FLYTERM_OKX_CLI` only if the executable is not on PATH.
3. Keep the existing viewer and keeper service templates in plan mode. Use a reverse proxy with HTTPS for the final domain; the viewer listens on loopback. Secrets remain in the server's protected environment files.
4. The user creates the official IGNIX token. Verify the current System Vault registration, wGOOGLx quote, 100/100 bps tax, zero holder share and the intended creator. Record the actual creation receipt; never promote a trial CA by changing its label.
5. Prepare the latest contract deployment using fresh nonces and a new model run. `prepare-keeper` accepts `--tax-vault` for the verified vault. The X Layer hop operator must match the deployment's fixed execution operator. Keep exactly the two existing role wallets unless the user changes that choice.
6. Compare deployed runtimes, constructor bindings and proxy implementations with the reviewed release; then `pin-runtime` records all execution and read dependencies. Pinning alone is not a source audit. New v0.4.3 contracts need deployment; local source does not upgrade any old contract.
7. Populate a private production instance file with `published:true`, `officialProduct:true`, `role:"production"`, chain 196, token, manager, registry, expectedFactory, vault, creator, quote, templateId 0, taxBuyBps/taxSellBps 100, dividendBps 0 and createTx. Set `FLYTERM_XLAYER_RPC`; serve with `--instance <file>` and explicit production `--run`/`--ops` directories.
8. Review actual principal, order/loss ceilings, quote/slippage caps, gas budget and key permissions. The generated profile is disabled and the sample budgets are not an instruction to trade. Perform one bounded funded acceptance of the exact deployed profile and its whole route, then enable the explicitly approved profile. Do not count the old manual wallet bridge as a project-hook deposit.
9. Confirm read-only public verification, funded accounting, restart/reconciliation behavior, pause and fixed-beneficiary recovery. Publish the corresponding sanitized source and run evidence with that release.

## Local validation

`forge test --summary`; Python unittest discovery; `npm test`; `npm run build`; `scripts/accept_v03_local.py` on ephemeral Anvil. The combined fixture uses directed signals and simulated external Core/Circle execution. It is not a new full-brain performance test or a mainnet claim.

## Boundaries carried forward

The full neural implementation is unchanged. Historical live runs require their archived source for replay. Old timelocked principal remains untouched. No artificial withdrawal delay is reintroduced. No new mainnet swaps, claims, bridge transfers, deployments or publication are part of this local release.

The earlier public Git history contains trial identity information. This release is a sanitized new tree; preparing it does not erase historical commits or third-party copies.
