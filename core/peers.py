"""Aodı-Hyperion — distributed inference peer client (stdlib urllib).

Same fleet contract as the rest of the Aodı suite: every registered device
exposes Ollama; capability tags steer candidate choice. A peer that cannot
generate is reported honestly — never silently degraded.
"""
import json, os, time, urllib.request

import config


def _req(method, url, payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def probe(node):
    t0 = time.time()
    entry = {"up": False, "latency_ms": None, "models": [],
             "load": _load_hint(), "battery": _battery_hint()}
    try:
        tags = _req("GET", node["ollama_url"].rstrip("/") + "/api/tags",
                    timeout=6)
        entry["up"] = True
        entry["latency_ms"] = int((time.time() - t0) * 1000)
        entry["models"] = [m.get("name", "?").split(":")[0]
                           for m in tags.get("models", [])]
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"[:120]
    return entry


def generate(node, system, prompt, expect_code=True, timeout=None,
             temperature=0.2):
    url = (node.get("ollama_url") or "").rstrip("/")
    if not url:
        return {"ok": False, "text": "", "node": node.get("name"),
                "model": None, "latency_ms": None,
                "error": "العقدة بلا محرك توليد (ollama_url فارغ)"}
    model = node.get("model") or "qwen2.5-coder"
    payload = {"model": model, "prompt": prompt, "system": system,
               "stream": False, "options": {"temperature": temperature,
                                            "num_ctx": 8192}}
    t0 = time.time()
    try:
        out = _req("POST", url + "/api/generate", payload,
                   timeout=timeout or config.GEN_TIMEOUT)
        text = (out.get("response") or "").strip()
        if expect_code:
            text = _strip_fences(text)
        return {"ok": True, "text": text, "node": node.get("name"),
                "model": model, "latency_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "text": "", "node": node.get("name"),
                "model": model, "latency_ms": int((time.time() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}"[:160]}


def _strip_fences(s):
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _load_hint():
    try:
        import os
        if hasattr(os, "getloadavg"):
            n = os.cpu_count() or 1
            return round(min(os.getloadavg()[0] / max(n, 1), 1.0), 2)
    except Exception:
        pass
    return 0.0


def _battery_hint():
    try:
        import subprocess
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                             text=True, timeout=3).stdout
        import re
        for line in out.splitlines():
            m = re.search(r"(\d{1,3})%", line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def nodes_from_registry():
    nodes = []
    reg = config.load_json(config.KEY_DIR.parent / "nodes.json", []) or []
    for n in reg:
        if isinstance(n, dict) and n.get("name"):
            nodes.append(n)
    return nodes


def mesh_feed():
    try:
        data = _req("GET", config.MESH_URL.rstrip("/") + "/hy/mesh/nodes",
                    timeout=4)
        out = []
        for n in data.get("nodes", []):
            out.append({"name": n.get("name"), "ollama_url": n.get("ollama_url"),
                        "tags": n.get("tags", []), "up": n.get("up", False),
                        "source": "mesh"})
        return out
    except Exception:
        return []


def topology():
    seen = set()
    nodes = []
    for n in nodes_from_registry():
        n.update(probe(n))          # merge liveness into the registry node
        nodes.append(n)
        seen.add(n.get("name"))
    for n in mesh_feed():
        if n.get("name") not in seen:
            nodes.append(n)
    return nodes
