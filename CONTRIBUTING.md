# Contributing — Aodı-Hyperion

The project holds a strict **stdlib-first, zero-dependency** discipline.
Respect it and your patch lands fast.

## Ground rules

1. **Python core**: standard library only (`http.server`, `sqlite3`,
   `secrets`, `subprocess`, `json`, `re`). No pip packages — this includes
   the zk layer (pure math stays in `core/zk.py`).
2. **Mesh**: Go standard library only (`crypto/ecdsa`, `crypto/x509`, …);
   `go.mod` stays dependency-free.
3. **Relay**: Node built-ins only (`http`/`https`), zero npm deps.
4. **Bounded autonomy**: any automated loop (mutations, attempts, workers)
   stays capped, logged and auditable. Never add an unbounded retry.
5. **Local-only data**: user code and verdicts never leave the machine.
6. **Behavioral truth**: never trust a model's self-report; add property
   cases instead. Fitness verdicts must be re-runnable in isolation.
7. **Dashboards must HTML-escape** every dynamic string.
8. **Docs in English** (README/WHITEPAPER/ARCHITECTURE/SETUP/CHANGELOG/
   CONTRIBUTING). Inline comments may be Arabic or English.

## Dev workflow

```bash
python3 tests/test_hyperion.py -v          # must pass offline (no Ollama)
cd mesh && gofmt -w . && go vet ./... && go build -o ../bin/hy-mesh .
node --check relay/relay.js
python3 core/server.py --port 9412         # manual dashboard check
```

## Pull requests

- One logical change per PR.
- CI runs: Python 3.11 tests + Go vet/build + Node syntax check.
- New mutation operators or fitness penalties: extend `core/evolve.py`,
  keep the operator named and bounded, and add a fixture case proving
  behavior remained truth-checkable.

## Reporting issues

Include OS, Go/Ollama versions, `hyctl lineage` output and (for sandbox
escapes) the exact candidate code + runner stderr.

## License

MIT © 2026 Baran Avisat. Contributions are accepted under the same license.
