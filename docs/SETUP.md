# Setup — Aodı-Hyperion

No pip, no npm, no Docker required. Python 3.8+, Node 18+ (relay only),
Go 1.21+ (mesh only).

## 1. Local inference (Ollama, free)

```bash
ollama pull qwen2.5-coder
ollama serve     # on every brain node
```

## 2. Signed mesh daemon (Go)

```bash
cd mesh
gofmt -w . && go vet ./... && go build -o ../bin/hy-mesh .
HY_NAME=gossip-1 HY_TAGS="gpu,lite" ./../bin/hy-mesh
```

| Env | Default | Meaning |
|---|---|---|
| `HY_ADDR` | `:9411` | mesh listen address |
| `HY_NAME` / `HY_TAGS` | hostname / `lite,gpu` | identity snapshot fields |
| `HY_KEY_DIR` | `.` | persistent ECDSA P-256 identity dir |
| `HY_PEERS` | — | seed peers csv (`http://ip:9411`) |
| `HY_HEARTBEAT_S` | `10` | heartbeat interval |

## 3. Organism core + dashboard (Python)

```bash
python3 core/server.py --port 9412
open http://127.0.0.1:9412/
```

| Env | Default | Meaning |
|---|---|---|
| `HY_HOME` | `~/.hyperion` | state: hyperion.db, keys/, artifacts/ |
| `HY_MESH_URL` | `http://127.0.0.1:9411` | signed-gossip feed |
| `HY_GENERATIONS` / `HY_POPULATION` | `6` / `5` | genetic engine bounds |
| `HY_SANDBOX_TIMEOUT` / `HY_SANDBOX_MEM_MB` | `15` / `384` | iso-verification limits |
| `HY_MAX_WORKERS` | `8` | tensor worker cap |
| `HY_TELEGRAM_RELAY` | — | `http://127.0.0.1:7412/emit` |
| `HY_TELEGRAM_TOKEN`/`HY_TELEGRAM_CHAT` | — | direct telegram mode |

## 4. Register a brain node + a tensor worker

```bash
python3 core/cli.py nodes add mac-local http://127.0.0.1:11434 gpu
# a second device (e.g., a laptop) can register as a tensor worker:
HY_PORT=9413 python3 core/server.py --port 9413   # same binary, worker role
curl -X POST :9412/api/workers -d '{"name":"laptop","url":"http://192.168.1.117:9413/api/worker/mmul"}'
```

## 5. Drive the organism

```bash
python3 core/cli.py run "write a function that dedups a list preserving order" order_dedup
python3 core/cli.py evolve 3 5
python3 core/cli.py tensor 24 2
python3 core/cli.py attest README.md first-seal
python3 core/cli.py verify-attest last
python3 core/cli.py lineage
```

## 6. Phone alerts (Telegram)

- Relay mode: `TELEGRAM_TOKEN=… TELEGRAM_CHAT=… node relay/relay.js`
  and `HY_TELEGRAM_RELAY=http://127.0.0.1:7412/emit`.
- Direct mode: `HY_TELEGRAM_TOKEN` + `HY_TELEGRAM_CHAT` on the core.

## 7. Tailscale (recommended)

Install Tailscale on every device (free personal mesh). Use the 100.x.y.z
tailnet IPs for `HY_PEERS`, node registration and worker URLs.

## Support

baranavisat@gmail.com · WhatsApp +90 531 326 37 22 (wa.me/905313263722)
MIT © 2026 Baran Avisat
