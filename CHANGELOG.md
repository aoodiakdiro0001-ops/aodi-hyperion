# Changelog — Aodı-Hyperion

## 1.0.0 — 2026-10-25

First public release — the honest zero-knowledge self-evolving organism.

### Mesh (Go stdlib)
- Signed gossip daemon: persistent ECDSA P-256 identities, per-round signature
  verification, 3-miss liveness, `/hy/mesh/state|nodes|peers|health`.
- Unverified snapshots never enter the node table (counted honestly as misses).

### Core (Python stdlib)
- Real ZK attestations: non-interactive Schnorr (Fiat–Shamir, sha256) inside
  RFC 3526 2048-bit MODP; offline verification; identity keys persisted once.
- The organism: Builder → sandbox verification (property tests in isolated
  `python -I` with rlimits) → repaired by Healer (≤2 bounded attempts) →
  Critic heuristics → verdict sealed by zk proof + lineage chain append.
- Real genetic engine: populations of executable genomes, 5 bounded mutation
  operators, elite crossover, kill-weakest, per-generation lineage sealing;
  recorded demo: best fitness 1.000 (clean-pass) within 3 generations.
- Real tensor sharding: K*K block matmul across remote workers + callable
  workers, round-robin distribution, result verified against local reference.
- sha256 lineage chain (tamper-evident, offline-verifiable) with first-broken-
  link reporting; SQLite storage (classes: organisms, candidates, lineage,
  attestations, events); non-blocking Telegram telemetry (optional).
- hyctl CLI: status / nodes / run / evolve / tensor / attest / verify-attest /
  lineage / serve / worker.

### Relay (Node, zero deps)
- Telegram Bot notification relay with buffer, `/emit` `/last` `/health`.

### Optional public anchoring
- `ledger-solidity/HyperionLedger.sol`: pin the local lineage head on any EVM
  testnet.

### Known limitations (explicit)
- ZK = sigma-protocol attestations (identity binding), not SNARK circuits.
- Post-quantum signatures are protocol-slotted, not implemented (no stdlib).
- Tensor sharding distributes numerical math, not LLM weights.
- Tasks live in process memory; lineage/attestations/candidates persist in
  SQLite.
