#!/usr/bin/env python3
"""Aodı-Hyperion — organism core API server (stdlib only).

Endpoints:
  GET  /api/state            organism + zk protocol + lineage head
  POST /api/organism/run     {goal, function?} → swarm task (async)
  GET  /api/organism/<tid>   stages/verdict/attestation
  GET  /api/organism         task list
  POST /api/evolve           {generations?, population?} → genetic run
  GET  /api/evolve/latest    last evolution stats
  POST /api/workers          {name, url} register a remote tensor worker
  GET  /api/workers          registered workers
  POST /api/tensor           {n?} sharded matmul across workers + verify
  POST /api/worker/mmul      embedded worker turn (block partial product)
  POST /api/attest           {label, path?} → zk attestation + lineage seal
  GET  /api/attestations     list with offline verifiability
  GET  /api/lineage          rows + chain verify
  GET  /api/events           telemetry tail
  GET  /                     dashboard (dir=rtl)
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CORE = "/".join(__file__.split("/")[:-1])
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import config
import agents
import evolve
import storage
import tensor
import telemetry
import verify
import zk

STATIC = os.path.join(os.path.dirname(CORE), "dashboard")

# RFC 7230: header safe ASCII only — brand stays inside UTF-8 bodies.
SERVER_NAME = "AodiHyperion/%s" % config.VERSION

WORKERS = {}   # name → {"url":..., "registered": ts}
EVOLVE_LAST = {"result": None}


class Handler(BaseHTTPRequestHandler):
    server_version = SERVER_NAME

    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/state":
            att = agents.attestor()
            vh = storage.verify_lineage()
            return self._json(200, {
                "brand": config.BRAND, "version": config.VERSION,
                "mesh": config.MESH_URL,
                "zk": zk.protocol_shape(),
                "lineage": {"size": vh.get("size"), "ok": vh.get("ok"),
                            "head": (vh.get("head") or "")[:16]},
                "attestor_y": zk.commit_public(att),
                "workers": list(WORKERS),
            })
        if p == "/api/organism":
            return self._json(200, {"tasks": agents.all_tasks()})
        if p.startswith("/api/organism/"):
            rec = agents.get(p.rsplit("/", 1)[1])
            return self._json(200 if rec else 404,
                              rec or {"error": "not found"})
        if p == "/api/evolve/latest":
            r = EVOLVE_LAST["result"]
            return self._json(200 if r else 404, r or {"error": "no run yet"})
        if p == "/api/workers":
            return self._json(200, {"workers": WORKERS})
        if p == "/api/attestations":
            return self._json(200, {"attestations": storage.list_attestations()})
        if p == "/api/lineage":
            vh = storage.verify_lineage()
            return self._json(200, {"rows": storage.lineage_rows(20),
                                    "verify": vh})
        if p == "/api/events":
            return self._json(200, {"events": storage.event_tail()})
        if p in ("/", "/dashboard"):
            return self._serve_dashboard()
        return self._json(404, {"error": "no route"})

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        body = self._body()
        if p == "/api/organism/run":
            goal = (body.get("goal") or "").strip()
            if not goal:
                return self._json(400, {"error": "goal required"})
            fn = (body.get("function") or "").strip() or None
            cases = body.get("cases")
            if isinstance(cases, list):
                norm = []
                for c in cases[:8]:
                    if isinstance(c, list) and len(c) == 2:
                        norm.append((c[0], c[1]))
                cases = norm or None
            else:
                cases = None
            return self._json(202, agents.new_task(goal, fn, cases))
        if p == "/api/evolve":
            g = int(body.get("generations", 0)) or None
            n = int(body.get("population", 0)) or None
            try:
                rep = evolve.evolve_population(generations=g, population=n)
                EVOLVE_LAST["result"] = rep
                telemetry.emit("evolve", "ok" if rep["ok"] else "warn",
                               "جيل وراثي: الأفضل %.3f بعد %d أجيال"
                               % (rep["best_fitness"], rep["generations"]))
                return self._json(200, rep)
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"[:200]})
        if p == "/api/workers":
            name = (body.get("name") or "").strip()
            url = (body.get("url") or "").strip()
            if not name:
                return self._json(400, {"error": "name required"})
            WORKERS[name] = {"url": url, "registered": __import__("time").time()}
            return self._json(200, {"ok": True, "workers": list(WORKERS)})
        if p == "/api/tensor":
            n = int(body.get("n", 0)) or 8
            K = int(body.get("blocks", 0)) or 2
            A = tensor.random_matrix(n)
            B = tensor.random_matrix(n)
            wks = list(WORKERS.values())
            workers = [w["url"] for w in wks if w.get("url")] or \
                      [tensor.block_matmul for _ in range(K)]
            try:
                out = tensor.shard_matmul(A, B, workers, K=K)
                ref = tensor.ref_matmul(A, B)
                out["verified"] = tensor.close(out["C"], ref)
                out.pop("C", None)
                out["workers_used"] = sorted(out.get("per_worker", {}))
                return self._json(200, out)
            except Exception as e:
                return self._json(502, {"ok": False, "error":
                                        f"{type(e).__name__}: {e}"[:200]})
        if p == "/api/worker/mmul":
            try:
                A, B = body["A"], body["B"]
                blk = tensor.block_matmul(A, B, int(body["r0"]), int(body["r1"]),
                                          int(body["c0"]), int(body["c1"]))
                return self._json(200, blk)
            except Exception as e:
                return self._json(400, {"error": f"{type(e).__name__}: {e}"})
        if p == "/api/attest":
            import hashlib as _h
            path = (body.get("path") or "").strip()
            label = (body.get("label") or "manual-seal").strip()
            if path:
                with open(path, "rb") as f:
                    sha = _h.sha256(f.read()).hexdigest()
            else:
                sha = (body.get("payload_sha256") or "").strip() or \
                      _h.sha256(json.dumps(body, sort_keys=True).encode()
                                ).hexdigest()
            key = agents.attestor()
            context = zk.context_for(sha, "attest", "hyperion-core")
            proof = zk.prove(key, context)
            okz = zk.verify(proof, context)
            aid = storage.add_attestation(label, None, "sealed", sha, proof) \
                if okz else None
            entry = storage.lineage_append("attestation", label, sha)
            return self._json(200, {"aid": aid, "zk_ok": okz, "lineage":
                                    entry, "context_sha256":
                                    __import__("hashlib").sha256(
                                        context.encode()).hexdigest()[:16]})
        return self._json(404, {"error": "no route"})

    def _serve_dashboard(self):
        import os
        idx = os.path.join(STATIC, "index.html")
        if os.path.exists(idx):
            with open(idx, "rb") as f:
                raw = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self._json(404, {"error": "missing dashboard"})

    def log_message(self, fmt, *args):
        pass


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="hy-core")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    a = ap.parse_args()
    httpd = ThreadingHTTPServer((a.host, a.port), Handler)
    print(config.banner(), flush=True)
    print(f"[core] listening http://{a.host}:{a.port} (HY_HOME={config.HOME})",
          flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
