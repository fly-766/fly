# Methods

## Model and sensory interface

The retained MaleCNS graph is represented by indexed neurons and directed synapses. Integration follows the pinned upstream Stonkfly controller and C++ memory kernel. Input normalization, unilateral luminance, the fixed motor readout, the gate, thresholds and neutral region are explicit engineering choices. The graph includes 166,700 retained neurons and 25,582,938 directed edges; sampled frontend telemetry is only a small fixed subset and must not be mistaken for the computed graph size.

The integration step is 0.1 ms and a controller observation advances 500 ms of neural time. DNp20 right-minus-left rates produce BUY/SELL proposals through the DNpe017 gate; HOLD is a valid outcome. New or opposite positions depend on account admissibility, not a forced neural output.

## Feedback and plasticity

Let $A_t=\mathrm{settledNet}_t-\mathrm{bookedCost}_t$. Feedback derives from $\Delta A_t=A_t-A_{t-1}$: reward at or above 0.01 USDC, aversive at or below -0.01 USDC, otherwise neutral. It is delayed accounting feedback, not a ground-truth label for the immediately preceding stimulus. The local [executable notation](../research/control.py) makes this rule explicit.

KC-to-MBON plasticity uses compartment-associated dopamine and filtered activity traces. This adaptation follows the upstream model implementation; anatomical correspondence does not establish biological or financial validity. Learned state is retained across observations within a run and restored from committed checkpoints after restart.

## Action space

The contract distinguishes signed long, flat and short states. A same-direction action adds only the gap between current marked notional and the equity-relative target, with native leverage 10 and reserve fraction at least 0.5. A contrary action is reduce-only. Unknown position changes quarantine the account instead of generating synthetic settlement. The position ROI stop compares loss with leverage-implied position margin; fees, latency and gaps can cause realized outcomes beyond the trigger.

Transport processing sizes, venue lot sizes and operating-gas budgets are separate from the absence of a fixed total-capital cap. Contract integer representations and venue constraints remain finite.

## Capital accounting and trust boundaries

Incoming BNB creator-tax proceeds travel through an external bridge and are credited only after actual USDC delivery. Deposits are principal, not trading gains. Profit eligibility is bounded by both settled earned surplus and equity above retained basis, and requires a flat, settled, consistent state. Recovery and profit have segregated exits and fixed recipients.

On BSC, a separately funded buyback budget uses delayed price observations, executable-quote checks and actual output balances. Prior to graduation, purchased tokens remain escrowed; a later transfer to the burn address is measured separately. A burn-address transfer is not a guarantee about market price.

The operator and creator wallet remain trusted during transport. Receipt matching supports auditability but does not transform an operator-mediated route into a trustless bridge. See [Disclosure](../DISCLOSURE.md).

## Evaluation protocol

Evaluate the adaptive model against frozen weights, feedback-shuffled controls, a neutral policy and passive exposure. Split observations chronologically, freeze the selection procedure before examining held-out outcomes, include fees and failed executions, and report uncertainty and sensitivity to market regimes. Never convert software tests or a visually active graph into performance evidence.

## Verification model

Separate five statements: input identity, source identity, deterministic replay, external commitment consistency, and financial execution. Only the evidence appropriate to each statement can support it. The [recording verifier](../scripts/replay_recording.py) reports the exact prefix it recomputed; no stronger claim is inferred.

## Production scheduling and observation time

The [BSC scheduler](../scripts/bsc_live_scheduler.py) completes pending transactions and account settlement before attempting another operation. Once the account is settled and funded, it prioritizes a valid recorded neural commitment over starting another tax or transport batch. A new observation is evaluated at most once per scheduling minute on this priority path; HOLD and ineligible signals return control to transport processing.

Commit construction reads a fresh HyperEVM block after neural observation. The block captured before market retrieval may predate the input timestamp, so using that older snapshot can delay a valid commitment. Observation timestamps, the original expiry window, nonce checks, order preview, and position risk controls remain unchanged. The adapter does not modify the neural controller or its frozen source manifest. [Scheduler regression checks](../scripts/test_bsc_live_scheduler.py).
