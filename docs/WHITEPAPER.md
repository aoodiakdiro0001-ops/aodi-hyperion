# WHITEPAPER — Aodı-Hyperion v1.0.0
### The Zero-Knowledge Self-Evolving Neural Organism & Cryptographic Mesh

*Honest engineering edition: every capability below is what actually runs.*

---

## 1. Thesis

AI agents that write code today are graded by unreliable witnesses (the
executing interpreter, the model describing its own output). Hyperion replaces
that with a machine-local organism where:

- **identity is cryptographic** (every corpus node and every verdict is signed
  or zero-knowledge-attested),
- **evaluation is behavioral** (isolated sandbox property tests, never believes
  an LLM's self-report),
- **retention is tamper-evident** (append-only hash-chain lineage),
- **improvement is algorithmic** (evolutionary selection, not vibes).

Everything runs inside your devices. The org never calls paid APIs and never
uploads user code.

## 2. System anatomy

```
                 [ mesh (Go) :9411 — signed gossip, ECDSA P-256 ]
                        │ verified heartbeats (authenticity)
                        ▼
   [ core (Python) :9412 — THE ORGANISM ]
   ┌────────────────────────────────────────────────────────────┐
   │ agents:  Builder → sandbox-verify → Healer ≤2 → Critic     │
   │ evolve:  population(genome) → mutate → fitness → kill/cross│
   │ zk:      Schnorr σ-protocol attestation of every verdict   │
   │ tensor:  K*K matmul blocks -> fleet workers -> verify       │
   │ lineage: sha256 chain (SQLite) → optional EVM anchor       │
   └────────────────────────────────────────────────────────────┘
                        │ telemetry
                        ▼
            [ relay (Node) :7412 → Telegram → your phone ]
```

## 3. The zero-knowledge layer (exact math)

Choose the RFC 3526 Group 14 prime p (2048-bit), generator g = 2.
The organism's attestor holds x; publishes y = g^x.

To seal a verdict with payload hash h and context
`c_text = "kind:owner:h"`:

1. k ← random in [1, q−1] where q = (p−1)/2 (we sample [1, p−2])
2. r = g^k mod p
3. challenge c = H(y, r, c_text) mod q  (Fiat–Shamir replace the verifier)
4. s = (k + c·x) mod q

Verification (offline, no secret): g^s ≟ r · y^c mod p.

Properties delivered and tested:
- **Completeness** — honest attestor always passes (`test_prove_verify_roundtrip`).
- **Soundness** — a forged s fails; a different context fails
  (`forged s`, `foreign-ctx` both reject in tests).
- **Honest-verifier zero-knowledge** — the transcript (y, r, c, s) reveals
  nothing about x; the serialized attestation never contains the secret
  (`test_public_key_never_reveals_secret`).

Honest limits: σ-protocols prove *knowledge/attestation statements*, not
arbitrary computation. Circuit-level zk (SNARKs/STARKs) requires foreign
dependencies and is consciously excluded by the stdlib-first rule; it is
slotted as future work in the same API shape.

## 4. The genetic engine (what evolves)

Genome = the organism's own executable candidates (Python source). Rules:

1. Population initialized from the reference seed (guaranteed-fit baseline).
2. Mutation operators (bounded, reviewable): collection-mode switches,
   loop rewrites, precheck grafts, representation tweaks — each is a *named*
   code mutation, so evolution stays auditable.
3. Fitness = isolated sandbox property score (golden behavioral cases inside
   `python -I` with rlimits) − static-heuristic penalties + speed bonus.
   Fitness never trusts the builder's word.
4. Selection: kill weakest, keep elites, seed-baseline elitism (the reference
   always survives), crossover grafts collection behavior from elites.
5. Every generation's (best fitness, avg, verdict, payload sha256) is sealed
   into the lineage chain — evolution history becomes tamper-evident truth.

Recorded run (3 gens x pop 5): gen1 avg 0.886 -> gen2/3 avg 1.000 with
best fitness **1.000 clean-pass** from generation 1; total 0.37 s. The
reference-genome elitism keeps the seed baseline alive in every round.

## 5. Heterogeneous tensor sharding (real math over real nodes)

`C = A·B` with K spans per axis → K² blocks; block (i, j) is computed by
worker `jobs[(i·K + j) mod |workers|]`; workers are remote HTTP endpoints
(e.g., a second `hyctl worker --port 9413` on another device) or callable
in-process workers for tests. The organism **verifies** the assembled matrix
against a local reference before publishing any number.

Honest limits: this shards *numerical tensor operations* (the compute part),
not LLM weights. Weights-sharding would require a new inference executor and
is explicitly left to future work rather than faked.

## 6. The signed gossip mesh

Every mesh node generates a persistent ECDSA P-256 key. `/hy/mesh/state`
returns `sign(payload || ts || tags || load || pubkey)`. Receivers verify the
ASN.1 signature **every round**; only verified snapshots are ingested, and
three consecutive failures demote a peer DOWN. Trust-on-first-use of peer
public keys is documented as a deliberate v1 decision (TOFU + tailnet).

Post-quantum: NIST kyber/dilithium-style lattice signatures have no Go-stdlib
implementation; the signedState contract keeps exactly one field-separable
payload so a drop-in Lattice signer can replace ECDSA without protocol
redesign. Claiming "quantum-resistant" today would be dishonest; building the
replaceable slot now is not.

## 7. Data, persistence, threat model

- `HY_HOME` (default `~/.hyperion`): SQLite db, attestor key, artifacts.
- Lineage chain: `hash = sha256(prev ‖ payload_sha256 ‖ kind ‖ label)`;
  verification walks the full chain and reports the exact broken link —
  demonstrated by the tamper test.
- Optional public anchor: `HyperionLedger.sol` pins the current head hash on
  any testnet; everything else stays local.
- Threat model: the sandbox assumes arbitrary untrusted code and contains it
  (resource limits + subprocess group kill + no-network `-I` child); the mesh
  assumes hostile HTTP assumes-line between peers (signatures), with transport
  privacy delegated to the tailnet.

## 8. What this is NOT (explicit)

- Not a model-weights partitioner, not a distributed inference accelerator.
- Not a blockchain: local tamper-evident ledger + optional public anchoring.
- Not an automated exploit factory: verdicts include static heuristics for
  dangerous patterns and the sandbox is read-only-unwilling-by-design.

---

*Documented live demo numbers and their provenance live in the repository's
recorded benchmark section (README) — every number traces to an HTTP response
or a measured wall-clock sample on the author's machine.*
