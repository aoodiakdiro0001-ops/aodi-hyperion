# Aodı-Hyperion — live examples for demos and tests

## 1. Organism run (goal → build/verify/heal → zk-sealed verdict)

```bash
python3 core/cli.py nodes add mac-local http://127.0.0.1:11434 gpu
python3 core/cli.py run "write a function that dedups a list preserving order" order_dedup
```

Watch the dashboard: stages build → verify → (heal) → critic, plus the
attestation badge. The final verdict is bound by a Schnorr zero-knowledge
proof — verify it offline:

```bash
python3 core/cli.py verify-attest last
```

## 2. Genetic engine (real code evolution)

```bash
python3 core/cli.py evolve 3 5
# recorded demo: best fitness reaches 1.000 clean-pass, each generation sealed
```

## 3. Tensor sharding across devices

```bash
# second device (laptop):
python3 core/server.py --port 9413          # worker role (same file)
# host:
curl -X POST :9412/api/workers -d \
  '{"name":"laptop","url":"http://192.168.1.117:9413/api/worker/mmul"}'
python3 core/cli.py tensor 24 2
```

## 4. Signed mesh (authentic gossip)

```bash
cd mesh && go build -o ../bin/hy-mesh .
HY_NAME=node-a ./../bin/hy-mesh
HY_NAME=node-b HY_ADDR=":9412" HY_PEERS="http://127.0.0.1:9411" ./../bin/hy-mesh
# every heartbeat verifies the peer's ECDSA P-256 signature; GET /hy/mesh/nodes
```

## 5. Lineage chain (tamper-evident)

```bash
python3 core/cli.py lineage
# modify one byte in ~/.hyperion/hyperion.db → verify reports the exact link
```
