# Verification

Do not take the website as evidence. The checks below can be repeated on a public explorer and a public RPC.

## 1. Token and vault

Explorer (X Layer):

- Token: https://www.okx.com/web3/explorer/xlayer/token/0xbf273d796a2eb31ac20015dcdc861b23df30eeee
- Vault: https://www.okx.com/web3/explorer/xlayer/address/0x6248a016d7ed2dfac1560bf1e15da39b440b5531
- Creation: https://www.okx.com/web3/explorer/xlayer/tx/0x5138e600a6e7124a79194f78cdf96fa15a53e3aebf0d4327a536fca453447d91
- Vault sync: https://www.okx.com/web3/explorer/xlayer/tx/0x5a23203b9de579eed1f7425dcd417ebf92813939c095c96f07a80ac7d1c1ce7b
- Creator claim: https://www.okx.com/web3/explorer/xlayer/tx/0xf7de32028e30e344458e33a93fc2f5f9e5030bdbda5417007f3feea9b15e4d52

IGNIX index: https://api.ignix.bot/v1/launches/0xbf273d796a2eb31ac20015dcdc861b23df30eeee

On the vault, confirm:

```text
TOKEN()          == 0xbf273d796a2eb31ac20015dcdc861b23df30eeee
QUOTE()          == 0xf8c5308F80E459bb53d9EbE689854d9cBb2Caa6f
CREATOR()        == 0xD3050fbDd30bA35397E9b2FCf028978b85472B11
DIVIDEND_BPS()   == 0
```

On IGNIX manager `0x96b51c57e5346d0c0198899243cf851d1e23c309`, `tokens(token)` should report buy and sell tax of `100` bps and the same quote and creator.

The file [`config/ignix-instance.json`](config/ignix-instance.json) is labeled `officialProduct: false`. If a later token is issued, that flag and these addresses must change together.

## 2. Quote asset and bridge path

Public protocol addresses are pinned in [`config/protocol-addresses.json`](config/protocol-addresses.json).

| Role | Address |
|---|---|
| wGOOGLx | `0xf8c5308F80E459bb53d9EbE689854d9cBb2Caa6f` |
| Native USDC on X Layer | `0xB6CEceAB302E2E4948951eE7843FC24E92933061` |
| CCTP TokenMessengerV2 | `0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d` |
| HyperEVM USDC | `0xb88339CB7199b77E23DB6E890353E22632Ba630f` |
| HyperEVM MessageTransmitterV2 | `0x81D40F21F12A8F0E3252Bccb954D722d4c464B64` |
| CCTP domains | X Layer `37` → HyperEVM `19` |

Circle references:

- https://developers.circle.com/cctp/references/contract-addresses
- https://www.circle.com/fr/blog/now-available-native-usdc-cctp-on-x-layer

## 3. Path demonstration (not token tax)

These transactions show that wGOOGLx can be converted to native USDC and minted on HyperEVM. They are not creator tax from the test token.

| Step | Hash |
|---|---|
| OKB → wGOOGLx | [`0xe169d969…`](https://www.okx.com/web3/explorer/xlayer/tx/0xe169d96917767ec8addacf41ca338db8fe4bc8d400c629841c0e192d0cf01015) |
| wGOOGLx → USDC | [`0x91873b7c…`](https://www.okx.com/web3/explorer/xlayer/tx/0x91873b7cb8f4ae685440479aff91caa9a3c40514365ac6f61be08fbc7341777e) |
| USDC approve messenger | [`0x34fdc6ea…`](https://www.okx.com/web3/explorer/xlayer/tx/0x34fdc6ea6f586c4efe37fe3ea9a1013700e714022e9b02648e0f7f9fefa1c81c) |
| `depositForBurn` | [`0xd14e6b9b…`](https://www.okx.com/web3/explorer/xlayer/tx/0xd14e6b9be8005e23092344e6a8b927978ce33a1faf64ce174c5d73d5b29aa49c) |
| HyperEVM `receiveMessage` | [`0xd16b6890…`](https://www.hyperscan.com/tx/0xd16b68902c6cd547afcd4fe069fc32434b371a3690bf3561f3c070becc5d230f) |

Machine-readable copy: [`config/path-demonstration.json`](config/path-demonstration.json).

## 4. Source in this repository

- Hop, tax conversion, CCTP ingress, trading account, recovery, and buyback: `contracts/src/v03/` and `contracts/src/v04/`
- Unarmed operator planning (environment-variable key files, never committed): `flyterm/ops/`
- Live reader for the test instance: `flyterm/launch_status.py`

Keeper configurations generated from source set `liveEnabled` to `false`. Presence of Solidity or Python here is not evidence that a mainnet keeper is armed.

## 5. Still unproven

- Official token launch
- Tax from this test token bridged as HyperEVM principal
- Live buyback of this test token from realized Hyperliquid profit
- Continuous on-chain anchoring of neural records
