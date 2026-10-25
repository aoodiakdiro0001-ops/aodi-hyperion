# BENCHMARKS — Aodı-Hyperion v1.0.0

All numbers below come from the **live organism demo** on the author's
MacBook (M-series · Python 3.8 · Go 1.21 · Ollama `qwen2.5-coder` · SQLite in
`~/.hyperion`). Every row is a recorded HTTP response or a measured
wall-clock sample — nothing was simulated in a spreadsheet.

## The live dashboard (final capture)

| Metric | Value | Source |
|---|---|---|
| ZK attestations stored | **3** (organism verdicts + offline file seals) | dashboard card / `GET /api/attestations` |
| Lineage chain | **12 links ✓** (`verify.ok = true`) | dashboard card / `GET /api/lineage` |
| Best genetic fitness | **1** (clean-pass, 3 generations) | dashboard card / `GET /api/evolve/latest` |
| Signed mesh | node-b UP · **verified-handshakes = 18** (ECDSA P-256 per round) | `/hy/mesh/nodes` |
| Organism task | `52af238fbc` · done · **clean-pass · zk ✓** | dashboard task list |

![Live organism dashboard](assets/dashboard-live.png)

## Zero-knowledge layer (the real crypto)

10 prove + verify cycles on the RFC 3526 "Group 14" 2048-bit MODP group,
pure Python integer arithmetic, single MacBook core:

| Metric | Value |
|---|---|
| `prove()` avg | **27.2 ms** |
| `verify()` avg (offline check) | **31.9 ms** |
| Soundness spot-check | forged `s` and foreign context both **reject** |
| Secret leakage | the serialized transcript never contains `x` (unit-tested) |

**Caught by our own tests:** the first draft accidentally encoded a
1536-bit prime; `test_protocol_shape` (asserting `bits == 2048`) failed
immediately and the modulus was replaced with the exact RFC 3526 Group 14
value. Tests guard real math, not style — prove cost rose from ~12 ms to
~27 ms after the fix, the honest price of the real 2048-bit group.

## Organism runs (builder -> sandbox -> critic -> zk seal)

Recorded on the live core (:9412, brain registered + running worker core):

| Task | Path | Result |
|---|---|---|
| `52af238fbc` (API, warm brain) | build 2,872 ms -> sandbox **44 ms** -> critic 3/3 | **done 3,018 ms** · clean-pass · **zk True** |
| `51b7ce74f6` (CLI, cold-ish brain) | build 36,043 ms -> sandbox 70 ms -> critic 3/3 | **done ~36.4 s** · clean-pass · **zk True** |

Note: build time is local Ollama generation speed (RTT-free loopback), not
organism overhead — the warm second run is ~12x faster. Hyperion's own
overhead (isolated verify + ZK attestation + lineage seal) is **44-70 ms**.

## Real genetic engine (3 generations x population 5)

Recorded run (366 ms total wall clock):

| Gen | best | avg | verdict |
|---|---|---|---|
| 1 | 1.000 | 0.886 | clean-pass |
| 2 | 1.000 | 1.000 | clean-pass |
| 3 | 1.000 | 1.000 | clean-pass |

Each generation appended a lineage link (`evolution-generation` + winning
payload sha256); `verify_lineage()` walks all links and passes. The seed
baseline itself is always clean-pass 1.000 (enforced by
`test_seed_baseline_is_truth`) and survives every round via elitism.

## Tensor sharding (real distributed math)

| Run | Detail |
|---|---|
| 24x24, K=2, one remote HTTP worker (`worker-9413/api/worker/mmul`) | **4 blocks / 9 ms** · `verified=true` — assembled C matches the local exact reference |
| In-process callables, K=2 (unit test) | 4 blocks, round-robin per worker 2/2, matches reference |
| 9x9, K=3 (unit test) | **9 blocks** match the reference exactly |

Honest note: `worker-9413` is a second **core process** on the same machine
(the sleeping-laptop peer was DOWN at demo time); the protocol path is
identical to a real second device (one HTTP POST per block, silently
refusing any local fallback re-computation).

## Signed gossip mesh (authenticity per heartbeat)

| Metric | Value |
|---|---|
| Signature scheme | ECDSA P-256 (ASN.1) over sha256(snapshot) — Go stdlib |
| Verified handshakes in demo | **18** on node-b (`peers_verified = 1/1`) |
| Unverified snapshots | **never** enter the node table (counted as misses) |
| Liveness rule | 3 consecutive failed rounds -> DOWN |

Honest scope (documented, not faked): transport privacy rides on the
tailnet; post-quantum lattice signing has no stdlib implementation and is
protocol-slotted, not claimed.

## Lineage chain + offline attestation

| Action | Result |
|---|---|
| `attest README.md readme-seal` | sealed sha `b2a87404a61b9503…` · **zk OK** · aid 2 · lineage idx 5 |
| `verify-attest last` | **zk VALID (offline)** |
| Chain verify (12 links) | `ok = true`, head `1611bb95…` |
| Tamper test (unit) | one flipped payload byte -> `ok = false`, `broken_at_idx` = exact link |

## Sandbox (behavioral truth, bounded)

| Property | Value |
|---|---|
| Child process | `python -I` (no site/user paths) with a probe harness |
| Limits | RLIMIT_AS 384 MB · RLIMIT_CPU 15 s · RLIMIT_NPROC 24 · RLIMIT_CORE 0 · process-group kill |
| Measured verify latency in live tasks | **44-70 ms** per candidate |
| Static heuristics | 7 named rules (HY-D01..D07); live clean builds = **0 findings** |
| Truth enforcement | crashing / partial candidates never score a pass (unit-tested) |

## Test battery

`python3 -m unittest tests.test_hyperion`: **14/14 OK in ~1.1 s**, fully
offline (no Ollama needed, every test isolates `HY_HOME` into a temp dir),
plus `gofmt/vet/build` clean and `node --check` clean.

## Honest scope of the whole system

- ZK here = a Schnorr / Fiat–Shamir **attestation of identity + verdict
  binding** — not a SNARK circuit compiler; rich circuit-zk needs foreign
  dependencies and is deliberately outside the stdlib-only discipline.
- Tensor sharding distributes **numerical matmuls**, not LLM weights.
- "Self-evolving" = evolution of executable code genomes under behavioral
  fitness — not neural-weight mutation.
- Tasks live in process memory; the lineage chain, attestations and genetic
  candidates persist in SQLite (see ARCHITECTURE.md).
