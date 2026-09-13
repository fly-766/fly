# Security

This tree must not contain private keys, seed phrases, keystore passwords, RPC credentials, or operator journals.

Keeper and model signers, when used, read key material from environment variables (`FLYTERM_KEEPER_KEY_FILE`, `FLYTERM_MODEL_KEY_FILE`, `FLYTERM_SETTLEMENT_KEY_FILE`) pointing at files outside the repository. RPC endpoints are likewise supplied through environment variables.

Generated keeper profiles set `liveEnabled` to `false`. Arming a live signer is a separate, explicit operation and is not performed by cloning this repository.

The HTTP viewer binds to loopback and does not expose exchange, approve, or broadcast routes.

If a secret is committed, rotate it and report the commit privately. Do not paste keys into issues or pull requests.
