#!/usr/bin/env python3
"""Aodı-Hyperion — hyctl CLI (stdlib only).

  hyctl status                     organism + lineage + workers
  hyctl nodes add <name> <url> [tags]
  hyctl run "<goal>" [function]    builder→critic→healer with zk attestation
  hyctl evolve [gens] [population] genetic engine live
  hyctl tensor [n] [blocks]        sharded matmul across registered workers
  hyctl attest <path> [label]      zk proof sealing a file digest
  hyctl verify-attest <aid… or last>  offline zk proof check
  hyctl lineage                    chain links
  hyctl serve                      start core on :9412
  hyctl worker                     start an additional worker core (same file)
"""
import json, os, sys

CORE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CORE)
import config
import storage
import tensor
import zk


def cmd_status():
    print(config.banner())
    for r in storage.lineage_rows(6):
        print("  sealed %-3d %-24s %s" % (r["idx"], r["kind"], r["hash"][:12]))
    atts = storage.list_attestations(5)
    print("[zk] protocol:", zk.protocol_shape()["protocol"])
    print("     attestations stored:", len(atts))
    at = storage.attestation_stats() if hasattr(storage, "attestation_stats") else None
    if at:
        print("     verified:", at)


def cmd_nodes(name, url, *tags):
    nodes = config.load_json(config.KEY_DIR.parent / "nodes.json", []) or []
    nodes = [n for n in nodes if n.get("name") != name]
    nodes.append({"name": name, "ollama_url": url,
                  "tags": [t for t in tags or ["lite"]]})
    config.save_json(config.KEY_DIR.parent / "nodes.json", nodes)
    print("registered", name, "→", url)


def cmd_run(goal, function=None):
    import agents, peers, time
    nodes = [n for n in peers.topology() if n.get("up") and n.get("ollama_url")]
    if not nodes:
        print("[fail] no live node — start Ollama + register with nodes add")
        return 1
    rec = agents.new_task(goal, function)
    print("task", rec["id"], "→ goal:", goal[:72])
    while True:
        time.sleep(1.5)
        r = agents.get(rec["id"])
        if r["status"] not in ("queued", "running"):
            break
    for s in r["stages"]:
        print("  %-7s %-6s %-70s %sms"
              % (s["kind"], "✓" if s["ok"] else "…", s["detail"][:70],
                 s.get("ms")))
    print("verdict:", r["verdict"], "| zk:", (r.get("attestation") or {})
          .get("zk_ok"), "| artifact:", r.get("artifact"))
    return 0


def cmd_evolve(gens, population):
    import evolve, time
    t0 = time.perf_counter()
    rep = evolve.evolve_population(generations=int(gens or 4),
                                   population=int(population or 5))
    dt = (time.perf_counter() - t0) * 1000
    print(json.dumps({k: rep[k] for k in ("best_fitness", "best_verdict",
                                          "generations", "population")},
                     ensure_ascii=False))
    for h in rep["history"]:
        print("  gen %02d best=%.3f avg=%.3f verdict=%s"
              % (h["gen"], h["best"], h["avg"], h["verdict"]))
    print("elapsed %.0f ms | sealed head %s" % (dt, rep["seal_head"]))


def cmd_tensor(n, blocks):
    import urllib.request
    A = tensor.random_matrix(int(n or 8))
    B = tensor.random_matrix(int(n or 8))
    url = "http://127.0.0.1:%d/api/tensor" % config.DEFAULT_PORT
    payload = json.dumps({"n": int(n or 8), "blocks": int(blocks or 2)}
                         ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as e:
        print("[fail] start hyctl serve first:", type(e).__name__, e)
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_attest(path, label="manual-seal"):
    import hashlib, agents
    agents.attestor()
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    key = agents.attestor()
    context = zk.context_for(sha, "attest", "hyperion-core")
    proof = zk.prove(key, context)
    okz = zk.verify(proof, context)
    if okz:
        aid = storage.add_attestation(label, None, "sealed", sha, proof)
    else:
        aid = None
    entry = storage.lineage_append("attestation", label, sha)
    print("sealed:", label, "sha", sha[:16], "zk", "OK" if okz else "REJECT",
          "aid", aid, "lineage idx", entry["idx"])


def cmd_check_attest(which="last"):
    atts = storage.list_attestations(40)
    if not atts:
        print("no attestations")
        return
    row = atts[0] if which == "last" else \
        next((a for a in atts if str(a["aid"]) == str(which)), atts[0])
    ctx = zk.context_for(row["payload_sha256"], "verdict"
                         if row["label"].startswith("task-") else "attest",
                         "hyperion-core")
    ok = zk.verify(row["proof"], ctx)
    print("attestation", row["aid"], row["label"], "→ zk",
          "VALID (offline)" if ok else "INVALID")


def cmd_lineage():
    vh = storage.verify_lineage()
    print("verify:", json.dumps(vh))
    for r in storage.lineage_rows(8):
        print("%3d %-24s %s" % (r["idx"], r["kind"], r["hash"][:16]))


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="hyctl",
                                 description="Aodı-Hyperion control plane")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    na = sub.add_parser("nodes"); na.add_argument("add")
    na.add_argument("name"); na.add_argument("url"); na.add_argument("tags",
                                                                     nargs="*")
    rn = sub.add_parser("run"); rn.add_argument("goal")
    rn.add_argument("function", nargs="?", default=None)
    ev = sub.add_parser("evolve"); ev.add_argument("generations", nargs="?",
                                                   default=None)
    ev.add_argument("population", nargs="?", default=None)
    tn = sub.add_parser("tensor"); tn.add_argument("n", nargs="?", default=None)
    tn.add_argument("blocks", nargs="?", default=None)
    at = sub.add_parser("attest"); at.add_argument("path")
    at.add_argument("label", nargs="?", default="manual-seal")
    ck = sub.add_parser("verify-attest")
    ck.add_argument("which", nargs="?", default="last")
    sub.add_parser("lineage"); sub.add_parser("serve")
    sub.add_parser("worker")
    a = ap.parse_args()
    if a.cmd == "status":
        return cmd_status()
    if a.cmd == "nodes":
        return cmd_nodes(a.name, a.url, *a.tags)
    if a.cmd == "run":
        return cmd_run(a.goal, a.function)
    if a.cmd == "evolve":
        return cmd_evolve(a.generations, a.population)
    if a.cmd == "tensor":
        return cmd_tensor(a.n, a.blocks)
    if a.cmd == "attest":
        return cmd_attest(a.path, a.label)
    if a.cmd == "verify-attest":
        return cmd_check_attest(a.which)
    if a.cmd == "lineage":
        return cmd_lineage()
    if a.cmd == "serve":
        import server
        server.main()
    if a.cmd == "worker":
        import server
        server.main()


if __name__ == "__main__":
    sys.exit(main() or 0)
