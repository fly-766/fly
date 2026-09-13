# Fly · Technical methods

**Connectome-driven control under verifiable capital constraints**

This note specifies the implemented controller, its financial action space and the limits of its evidence. Equations summarize the corresponding source; the pinned implementation and its numerical conventions are authoritative. This is a project methods note, not a claim of journal publication.

## 1. System formulation

Let $\mathcal G=(V,E,W^{(0)})$ denote the retained, directed MaleCNS graph. The imported model has $|V|=166{,}700$ and $|E|=25{,}582{,}938$. Retention of the graph does not imply complete knowledge of the animal's dynamics. Cell models, gain assignments, sensory projection and memory parameters remain approximations.

The controller–executor system is factored as

$$
I_t=\mathcal E(X_{\le t}),\qquad
(S_{t+1},\hat a_t)=\mathcal F_{\Theta}(S_t,I_t,\rho_t),\qquad
A_t=\mathcal A(\hat a_t,C_t;\Lambda).
$$

$X_{\le t}$ is the available market history; $I_t$ is the RGB stimulus; $S_t$ includes neural state, delayed events and plasticity traces; $C_t$ is the observed account state; $\Lambda$ is the execution policy. $\mathcal A$ may reject a proposal. Emergency recovery is a separate control path and does not require the neural controller to propose an exit.

The graph and controller originate in [Stonkfly](https://github.com/nftechie/stonkfly). Fly's contribution is the disclosed market transducer, retained-state recording, contract-account observer and constrained capital/execution composition. It does not claim authorship of the anatomical reconstruction or the upstream neural model.

## 2. Sensory transduction

Only candles whose close time is no later than the market provider's observation time are admitted. At least 62 completed candles are required. With log returns $r_t=\log(p_t/p_{t-1})$,

$$
\sigma_t=\max\left(\operatorname{std}_{\mathrm{population}}(r_{t-59:t}),10^{-6}\right),
\quad z_t=\frac{\log(p_t/p_{t-3})}{\sqrt 3\,\sigma_t},
\quad b_t=\operatorname{round}\!\left(235\min(|z_t|,1)\right).
$$

For the $320\times180$ RGB input, every channel receives the same value:

$$
I_t(x,y)=
\begin{cases}
128,&|z_t|<0.05,\\
b_t,&z_t\ge0.05\;\land\;x\ge160,\\
b_t,&z_t\le-0.05\;\land\;x<160,\\
0,&\text{otherwise}.
\end{cases}
$$

The equality cases follow the implementation's strict deadband comparison. A neutral field at zero and a dark, weak directional field just outside the deadband are different stimuli. This encoding introduces a short-horizon directional prior; it should be evaluated as part of the controller, not treated as a neutral measurement of market information.

The upstream visual projection maps the frame into identified sensory populations. It does not insert price, position or expected future return directly into the neural weight update. See [`sensory.py`](../flyterm/sensory.py) and [`visual.py`](../vendor/stonkfly/stonkfly/neural/visual.py).

## 3. Neural dynamics, decoding and candidate memory

### 3.1 Subthreshold dynamics

The C++ kernel implements event-driven, leaky integrate-and-fire dynamics with exact subthreshold evolution between relevant events. A continuous-time representation of its subthreshold update is

$$
\tau_m\dot V_i=V_{\mathrm{rest},i}-V_i+I_i+g_i-a_i,
\qquad\tau_s\dot g_i=-g_i,
\qquad\tau_a\dot a_i=-a_i.
$$

Synaptic events update conductance or modulation state after the configured delay. Threshold crossing, reset, refractory handling and KC adaptation are discrete events; these equations alone do not specify the simulator. The kernel preserves the 0.1 ms event schedule while skipping inactive neurons only under its stated no-firing bound.

| Quantity | Implemented setting |
|:--|:--|
| Model timestep | 0.1 ms |
| Membrane / synaptic time constants | 20 ms / 5 ms |
| Synaptic delay / refractory interval | 1.8 ms / 2.2 ms |
| Firing threshold | $V_i>-45$ mV |
| Resting potential | −52 mV; −60 mV for KCs |
| KC adaptation | 8 mV increment; 200 ms decay |
| Neural observation window | 500 ms simulated time |
| Plasticity rate-bin upper bound | 10 ms |

These are simulation parameters, not a claim that every reconstructed neuron has identical measured physiology. [`kernel.cpp`](../vendor/stonkfly/stonkfly/neural/kernel.cpp) and [`brain.py`](../vendor/stonkfly/stonkfly/neural/brain.py) define the discrete implementation.

### 3.2 Fixed neural readout

For output population $U$ and observation duration $T=0.5$ s, define

$$
\bar\nu_U=\frac{1}{|U|T}\sum_{i\in U}n_i,
\qquad\delta=\bar\nu_{\mathrm{DNp20},R}-\bar\nu_{\mathrm{DNp20},L},
\qquad g=\sum_{i\in\mathrm{DNpe017}}n_i.
$$

The readout emits BUY for $g>0$ and $\delta\ge2$ Hz, SELL for $g>0$ and $\delta\le-2$ Hz, and HOLD otherwise. Mean population rates prevent unequal population size from directly becoming a readout bias. The mapping from descending-neuron activity to a financial label is an engineering interpretation.

### 3.3 Restricted plasticity

The adapted memory rule applies to existing KC-to-MBON07/11 edges. Anatomical DAN-to-MBON contact fractions define compartment gains $G_{de}$. Let $k_e$ be the presynaptic KC rate and $\nu_d-\nu_{d,0}$ the baseline-centered DAN rate. Then

$$
d_e=\sum_dG_{de}(\nu_d-\nu_{d,0}),\qquad
\tau_k\dot{\widetilde k}_e=k_e-\widetilde k_e,\qquad
\tau_d\dot{\widetilde d}_e=d_e-\widetilde d_e.
$$

The efficacy states evolve as

$$
D_e=\eta(k_e\widetilde d_e-d_e\widetilde k_e),\qquad
\dot u_e=-u_e/\tau_u+D_e,\qquad
\dot w_e=(u_e-w_e)/\tau_w.
$$

For each rate bin, the code evaluates the nonlinear drive with midpoint traces and propagates the passive two-state system in closed form. Both efficacy states are clipped to $[-0.9,1]$, producing $W_e=W_e^{(0)}(1+w_e)\in[0.1W_e^{(0)},2W_e^{(0)}]$. The trace constants are $\tau_k=\tau_d=1$ s; $\tau_u=1800$ s and $\tau_w=0.05$ s. Time constants are in simulated time.

This centered rule is motivated by [Huang et al. (2024)](https://doi.org/10.1038/s41586-024-07819-w), with project/upstream assumptions about gains, bounds and transfer to the MaleCNS reconstruction. It is not an exact reproduction of the paper's reduced model. The frozen condition prevents efficacy-state updates; it is useful as a counterfactual control. See [`rule.py`](../vendor/stonkfly/stonkfly/neural/rule.py) and [`circuit.py`](../vendor/stonkfly/stonkfly/neural/circuit.py).

### 3.4 Accounting-derived reinforcement

Let $L_t=N_t-O_t$, where $N_t$ is settled trading net and $O_t$ booked operating cost. Relative to the preceding observation anchor,

$$
\Delta L_t=L_t-L_{t-1},\qquad
\rho_t=
\begin{cases}
\mathrm{reward},&\Delta L_t\ge0.01\ \mathrm{USDC},\\
\mathrm{aversive},&\Delta L_t\le-0.01\ \mathrm{USDC},\\
\mathrm{none},&\text{otherwise}.
\end{cases}
$$

The first observation uses a zero anchor. The anchor is advanced on every observation, so sub-deadband changes are not accumulated until they cross a threshold. A non-neutral stimulus is delivered for up to 200 ms of the neural window through the selected PAM11 or PPL101 populations. The labels refer to engineered reinforcement; no modeled pain experience is implied.

The signal aggregates accounting changes between observations. It can reflect booked costs and does not uniquely attribute an outcome to a particular decision or connection. Parameter adaptation therefore requires empirical evaluation independent of the existence of nonzero weight updates.

<a id="action-space"></a>

## 4. Action admissibility and the long–flat state space

The financial position variable is restricted to $q\ge0$. BUY can initiate exposure only from flat, subject to admissible equity and policy checks. SELL uses the held quantity and a reduce-only venue flag. A SELL proposal at $q=0$ fails the nonzero-position condition.

For an eligible entry, ignoring representation-scale factors but retaining quantity rounding,

$$
B^{\mathrm{entry}}=\min(M,100E/101),\qquad
q^{\mathrm{entry}}=\Delta_q\left\lfloor B^{\mathrm{entry}}/(p^{\mathrm{limit}}\Delta_q)\right\rfloor.
$$

$M$ is the configured order cap. The source enforces integer arithmetic, price rounding, lot size and minimum notional. The account also checks commit nonce, execution freshness, reference-price deviation, order cooldown, daily limits and unresolved operations. The 1× policy is an entry-exposure bound; it is not a guarantee against loss, execution failure or adverse fee/funding effects.

### Why SELL does not open a short

The neural decoder supplies three symbols; their financial semantics are imposed by the executor. In the current implementation, SELL means transition toward flat. This preserves a smaller state space for initial validation and avoids interpreting every negative readout as permission to create a new liability.

A short-enabled extension would require a signed position $q\in\mathbb R$, separate open/reduce/close transitions, short-entry and exit cost accounting, partial-fill reconciliation, margin and liquidation checks, funding-cost handling, and long–flat–short evaluation controls. Changing the venue's reduce-only flag would not implement those properties. This documentation does not enable short trading.

<a id="capital-accounting"></a>

## 5. Capital basis and profit eligibility

The capital path and profit path are deliberately separate. Tax conversion proceeds enter the principal ledger, and CCTP messages carry a category and basis through the project route. The receiving contract checks the expected source, destination, asset, caller and message identity. External venue evidence is reconciled against account state.

Let $\mathcal F_t$ require a settled, flat account, no quarantined accounting, no unresolved principal/spot transfer, and positive eligible equity. With $D_t$ previously allocated profit,

$$
P_t=\begin{cases}
\max\{0,\min(N_t-D_t-O_t,E_t-B_t-O_t)\},&\mathcal F_t,\\
0,&\text{otherwise}.
\end{cases}
$$

The two terms bound return by both accounting profit and equity in excess of retained basis. New deposits do not become profit. Withdrawal, principal recovery, and buyback allocation are distinct state transitions.

The settlement signer remains trusted for parts of the venue evidence. Native account reads and reconciliation constrain the attestation; they do not eliminate that trust boundary. Gas paid externally is not automatically included in strategy P&L unless booked as operating cost.

Buyback contracts accept the designated profit return route and apply budget and price checks. Before graduation, acquired inventory is escrowed; post-graduation paths can deliver acquired tokens to the designated dead address. This is not a holder redemption entitlement. See [`TradingAccount.sol`](../contracts/src/v03/TradingAccount.sol), [`CctpIngress.sol`](../contracts/src/v03/CctpIngress.sol), [`ProfitBuyback.sol`](../contracts/src/v03/ProfitBuyback.sol) and the recovery variants under [`v04`](../contracts/src/v04/).

<a id="verification-model"></a>

## 6. Records, replay and trust boundaries

For record body $R_t$, the local commitment chain is

$$
H_0=\operatorname{SHA256}(\operatorname{canonicalJSON}(\mathrm{manifest})),\qquad
H_t=\operatorname{SHA256}(\operatorname{canonicalJSON}\{\mathrm{previous}:H_{t-1},\mathrm{body}:R_t\}).
$$

Canonicalization sorts JSON keys, uses compact separators and disallows non-finite numeric values. A record includes run identity, sequence, market observation, the content-addressed input image, pre/post state fingerprints, neural output, reinforcement and account snapshot. Model checkpoints support restoration; the observer rejects a resumed run when its declared model or runtime source differs.

The on-chain registry binds ranges of observations, previous and next roots, model identity, observation time, deadline and decoded side. A subset of observations can share a commitment range. This is a signed commitment protocol, not a zero-knowledge execution proof.

| Boundary | Assumption / limitation |
|:--|:--|
| Data | Hashes identify retained bytes; they do not establish market-feed truth |
| Computation | Replay is scoped to the recorded source, initial state and compatible environment |
| Numerical portability | Cross-machine bitwise identity is not claimed |
| Publication | An external head detects subsequent divergence; complete reporting is not guaranteed by local hashing |
| Execution | Submitted orders require terminal venue evidence and reconciliation |
| Settlement | Signer and protocol dependencies remain part of the trusted system |
| Production | Source availability does not establish a funded, continuously running deployment |

<a id="evaluation-protocol"></a>

## 7. Evaluation protocol

The following is a proposed evaluation design, not a results table.

**Mechanical acceptance.** Validate graph/source locks, stimulus construction, state restoration, record continuity, proposal/transaction binding, partial and rejected fills, unknown-outcome recovery, principal conservation, profit eligibility, and route replay protection.

**Controller evaluation.** Use chronological development and held-out periods. Fix encoders, thresholds, risk ceilings and transaction-cost assumptions before examining held-out outcomes. Include frozen efficacies, shuffled reinforcement, the disclosed sensory/readout baseline, cash and passive BTC exposure. An increase in profit alone does not identify plasticity as the cause.

**Reportable outcomes.** Report net return after costs, drawdown, exposure, turnover, trade count, action imbalance, rejection rate, stale-input rate, settlement failures and reproducibility failures. Preserve losing runs and parameter changes. Summarize uncertainty over market regimes and initial states; do not select a favorable trajectory as evidence of general performance.

**Open question.** Whether this adaptive connectome controller provides a useful out-of-sample trading advantage remains unresolved. Software tests and successful transfers answer different questions.

## Implementation map

| Specification | Source |
|:--|:--|
| Completed-candle encoding | [`flyterm/sensory.py`](../flyterm/sensory.py) |
| Full-controller wrapper and fingerprints | [`flyterm/neural.py`](../flyterm/neural.py) |
| Event-driven neuronal dynamics | [`kernel.cpp`](../vendor/stonkfly/stonkfly/neural/kernel.cpp) |
| Compartment selection | [`circuit.py`](../vendor/stonkfly/stonkfly/neural/circuit.py) |
| Plasticity traces and efficacy evolution | [`rule.py`](../vendor/stonkfly/stonkfly/neural/rule.py), [`brain.py`](../vendor/stonkfly/stonkfly/neural/brain.py) |
| Fixed neural decoder | [`controller.py`](../vendor/stonkfly/stonkfly/neural/controller.py) |
| Settled-ledger feedback and replay | [`flyterm/live.py`](../flyterm/live.py) |
| Content-addressed journal | [`flyterm/records.py`](../flyterm/records.py) |
| Entry bounds and reduce-only exits | [`TradingAccount.sol`](../contracts/src/v03/TradingAccount.sol) |
| Signed run commitments | [`RunCommitRegistry.sol`](../contracts/src/v03/RunCommitRegistry.sol) |
| Principal ingress and return categories | [`CctpIngress.sol`](../contracts/src/v03/CctpIngress.sol), [`CctpMessage.sol`](../contracts/src/v03/CctpMessage.sol) |
| Profit budgeting and repurchase | [`ProfitBuyback.sol`](../contracts/src/v03/ProfitBuyback.sol) |

## References and attribution

* **Male CNS Connectome Project.** [Dataset, release notes and attribution](https://male-cns.janelia.org/). The anatomical data is not produced by Fly.
* **nftechie / Stonkfly.** [Upstream source](https://github.com/nftechie/stonkfly). Retained graph simulation, controller and experimental memory implementation.
* **Huang, C., Luo, J., Woo, S. J., et al.** Dopamine-mediated interactions between short- and long-term memory dynamics. *Nature* **634**, 1141–1149 (2024). [DOI](https://doi.org/10.1038/s41586-024-07819-w). Biological results in that study do not validate financial learning in Fly.

Project source and newly drawn figures are MIT unless otherwise noted. Dataset and upstream licenses remain unchanged. Figure connectivity is schematic and is not a rendering of measured neuron coordinates or experimental performance.
