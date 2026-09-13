# Fly

Fly is an experimental trading laboratory. A publicly specified fruit-fly connectome proposes; a narrow contract envelope decides what capital is allowed to do.

Transfer tax collected on X Layer is intended to become Hyperliquid BTC principal. Realized profit, if any, is intended to return and repurchase the token. The connectome is a deterministic controller, not a claim of biological intelligence and not a forecast of return.

This repository exists so a third party can read the source, pin the addresses, and inspect the live test instance without trusting a landing page.

**The published IGNIX token is a parameter test. It is not the official product.**

## Independent verification

| Claim | Expected value | How to check |
|---|---|---|
| Chain | X Layer (`196`) | Any X Layer explorer |
| Token | [`0xbf273d796a2eb31ac20015dcdc861b23df30eeee`](https://www.okx.com/web3/explorer/xlayer/token/0xbf273d796a2eb31ac20015dcdc861b23df30eeee) | Token page; `name()` / `symbol()` currently `122` / `1221` |
| Vault | [`0x6248a016d7ed2dfac1560bf1e15da39b440b5531`](https://www.okx.com/web3/explorer/xlayer/address/0x6248a016d7ed2dfac1560bf1e15da39b440b5531) | `TOKEN()`, `QUOTE()`, `CREATOR()`, `DIVIDEND_BPS()` |
| Creator | `0xD3050fbDd30bA35397E9b2FCf028978b85472B11` | Vault `CREATOR()`; IGNIX manager `tokens(token).creator` |
| Quote asset | wGOOGLx `0xf8c5308F80E459bb53d9EbE689854d9cBb2Caa6f` | Vault `QUOTE()` |
| Buy / sell tax | 100 bps / 100 bps | IGNIX manager `tokens(token)` |
| Holder dividend | `0` | Vault `DIVIDEND_BPS()` |
| Vault template | System Vault / `templateId = 0` | Creation logs; [IGNIX launch API](https://api.ignix.bot/v1/launches/0xbf273d796a2eb31ac20015dcdc861b23df30eeee) |

Pinned files: [`config/ignix-instance.json`](config/ignix-instance.json), [`config/protocol-addresses.json`](config/protocol-addresses.json). Step-by-step notes: [`VERIFICATION.md`](VERIFICATION.md). Local page: `/verify.html`.

A successful creator `claim` does not mean tax has reached HyperEVM. Vault inventory may exist before it is credited to `creatorAccrued`.

## Intended route

```text
X Layer tax (wGOOGLx)
        │
        ▼
  creator claim
        │
        ▼
  wGOOGLx → USD → native USDC
        │
        ▼
  Circle CCTP V2  (domain 37 → 19)
        │
        ▼
  HyperEVM USDC → BTC perpetual principal
        │
        ▼
  realized profit only → wGOOGLx buyback
```

Reference transactions that demonstrate the wGOOGLx → USDC → HyperEVM path (not tax from the test token) are listed in [`config/path-demonstration.json`](config/path-demonstration.json).

Trading constraints in source: BTC only, long or flat, ≤1× leverage, ≤100 USDC per order. Keeper profiles are unarmed (`liveEnabled: false`) until a separately reviewed deployment is configured.

## What this is not

Fly is not Google, IGNIX, Circle, Hyperliquid, or Janelia. wGOOGLx is a wrapped stock token on X Layer; it is not listed equity. Replayable records and on-chain fingerprints are not zero-knowledge proofs of correct computation. A signed settlement is not a guarantee of venue fill quality. Nothing here is investment advice.

Full caveats: [`DISCLOSURE.md`](DISCLOSURE.md), [`docs/TRANSPARENCY.md`](docs/TRANSPARENCY.md).

## Repository

| Path | Contents |
|---|---|
| `contracts/` | Tax conversion, CCTP ingress, trading account, recovery, buyback |
| `flyterm/` | Connectome runtime, records, unarmed keeper planning |
| `config/` | Public addresses and the pinned test instance |
| `web/` | Local laboratory and verification page |
| `vendor/stonkfly/` | Upstream MaleCNS controller (MIT), without the large data files |

Connectome arrays are downloaded separately and checked against upstream locks. They are not stored in this tree.

## Local laboratory

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci --ignore-scripts
npm run build
python3 scripts/setup_contract_deps.py
python3 server.py --port 8798
```

Open `http://127.0.0.1:8798`. The HTTP server binds to loopback and exposes no signing or broadcast endpoints. `POST /api/exchange` is rejected.

```sh
forge test --summary
python3 -m unittest discover -s tests -v
npm test
```

X Layer fork tests are opt-in and read-only: `RUN_XLAYER_FORK=true forge test --match-path contracts/test/XLayerStableFork.t.sol -vv`.

## License

Project source is MIT. `vendor/stonkfly` retains its MIT license. MaleCNS v1.0 data remains under its upstream terms. See [`docs/PROVENANCE.md`](docs/PROVENANCE.md).
