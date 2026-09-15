# Independent recomputation

## Evidence input

Use a recording bundle containing manifest.json, records.json, artifacts/, and source/. Obtain its final record root from an independent reference, such as a published on-chain commitment. A hash supplied only by the same bundle is not an independent reference. No real recording or transaction history is included in this research repository.

1. Create an isolated Python environment compatible with the recording manifest. Install the bundle's requirements.txt, not an assumed system-wide dependency set.
2. Obtain MaleCNS data from the upstream download configuration and verify every declared checksum. The anatomical dataset is distributed separately under upstream terms.
3. Set STONKFLY_DATA to the verified dataset. For exact Linux replay, use the recording's matching kernel and metadata under the documented dataset cache directory, or compile the archived source. A different build or numerical environment must not be reported as an exact match.
4. Run `python scripts/replay_recording.py --bundle ./recording --expected-root <independent-root>` from this repository. This script accepts no wallet or transaction arguments.

## Verification order

The standalone verifier uses standard-library hashing to check the manifest-rooted record chain against the independent reference, then checks the archived source hashes before importing that source. It reconstructs the stimulus, derives the feedback from the recorded settled accounting, restores the initial state, reruns every neural window, and compares outputs, full-state fingerprints and telemetry arrays.

Successful output specifies runId, throughRound and head. It also reports venueIndependentlyVerified=false and computationProof=false. Exact replay verifies computation for that specified prefix; it does not independently authenticate the market feed, determine whether omitted rounds exist, prove venue fills or establish profitability.

## Source identity

The current research tree is an inspectable BSC methods snapshot. A historic or live recording must be replayed with the exact source and environment archived in that recording, not with arbitrary newer files from the default branch. Code availability, commitment integrity and financial correctness are distinct properties.
