# ARCHITECTURE — Aodı-Hyperion v1.0.0

## Key design decisions

1. **Go owns signed discovery, Python owns cognition.** The mesh daemon signs
   its own state snapshots and verifies peer snapshots on every heartbeat
   round. The core module owns agents, genetics, ZK attestations, tensor
   sharding and lineage persistence.

2. **Behavioral truth over self-reports.** Every candidate of the Builder is
   re-executed in an isolated `python -I` child with rlimits and property
   tests. Nothing "passes" because a model said so.

3. **Zero-knowledge where it is honest.** Attestation identity uses a real
   non-interactive Schnorr sigma protocol. Rich circuit-zk is excluded on
   purpose (stdlib-first) and slotted in the same API contract.

4. **Real evolution, auditable.** Mutation operators are named and bounded;
   fitness is measured behaviorally; every generation seals its stats into
   the lineage chain with the winning payload hash.

5. **Bounded autonomy everywhere.** Repair attempts ≤ 2, mutations ≤ 12 per
   child, workers ≤ 8, sandbox CPU/memory/fork caps, killpg on timeout.

6. **Signed mesh with TOFU honesty.** ECDSA P-256 persistent identities;
   unverified snapshots never enter the table. Post-quantum signer is
   protocol-slotted (payload contract stable).

## Task flow (organism run)

```
POST :9412/api/organism/run {goal, function?, cases?}
  → agents: pick fastest live node → peers.generate (Builder)
  → verify.verify_candidate: static heuristics + python -I property run
  → if verdict ≠ clean-pass: ≤2 Healer rounds (system prompt + failing detail)
  → Critic summary (static findings + test ratio)
  → zk attestor: proof = prove(x, context_for(sha, "verdict", "hyperion-core"))
  → storage: add_attestation + lineage_append (sha256 chain)
  → artifacts: ~/.hyperion/artifacts/<tid>/{name}.py + verdict.json
```

## Evolution flow

```
POST :9412/api/evolve {generations?, population?}
  → evolve_population: baseline seed check → population mutation
      → per-generation: elites + baseline + crossed/mutant kids
      → lineage_append("evolution-generation", …)
  → GET /api/evolve/latest (history arrays)
```

## Sharding flow

```
POST :9412/api/tensor {n, blocks}
  → shard_matmul(A, B, workers, K) over registered HTTP workers
      (worker default = embedded /api/worker/mmul turns; second core on
       another device registers via POST /api/workers)
  → verified against local reference before response
```

## SQLite schema

| table | purpose |
|---|---|
| organisms | swarm identities (public y) |
| candidates | genetic population + fitness per generation |
| lineage | sha256 hash chain of generations/attestations/seals |
| attestations | zk proofs (y, r, c, s) verifiable offline |
| events | telemetry tail |

## Explicit limits

- Tasks list is process-memory; restart loses the live list (lineage and
  attestations persist).
- Mesh transport privacy = tailnet; signatures provide authenticity only.
- LLM-cost surface: none for planning/fitness; only Builder/Healer
  generations call Ollama.
