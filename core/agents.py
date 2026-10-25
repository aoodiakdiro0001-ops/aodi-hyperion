"""Aodı-Hyperion — the organism: multi-agent swarm with zk-sealed verdicts.

Builders propose code (Ollama fleet), verification is REAL (sandbox property
tests + static heuristics), the Healer repairs with bounded attempts. Every
final verdict is bound to the organism's attestor identity through a Schnorr
zero-knowledge proof — verifiable offline, identity stays hidden.
"""
import hashlib, json, threading, time, uuid

import config
import storage
import telemetry
import peers
import verify
import zk

TASKS = {}
_TLOCK = threading.Lock()
_ATTESTOR = None

SYSTEM_BUILDER = ("أنت عضو بناء في كائن Hyperion. أخرج بايثون قابلة للتشغيل "
                  "فقط: الدالة الأولى التي يطلبها الهدف، بلا شرح. تعامل "
                  "بأمان مع المدخلات الفارغة والغريبة؛ بلا استدعاء شبكة ولا "
                  "حلقات بلا نهاية.")
SYSTEM_HEALER = ("أنت عضو إصلاح في كائن Hyperion. استلم الكود الفاشل وأعد "
                 "إصداره مُصلحاً مع الحفاظ على اسم الدالة وتوقيعها. بايثون "
                 "فقط بدون شرح ولا أسوار كود.")

DEFAULT_FUNCTION = "order_dedup"
DEFAULT_CASES = [
    ((["a", "b", "a", "c"],), ["a", "b", "c"]),
    (([],), []),
    (([1, 2, 2],), [1, 2]),
]


def attestor():
    """Organism identity: key persisted once, reused for every attestation."""
    global _ATTESTOR
    if _ATTESTOR is None:
        config.KEY_DIR.mkdir(parents=True, exist_ok=True)
        kfile = config.KEY_DIR / "attestor.json"
        secret = config.load_json(kfile)
        if not secret or "x" not in secret:
            secret = zk.keygen()
            config.save_json(kfile, secret)
        _ATTESTOR = secret
        storage.new_organism("core", "hyperion-core",
                             zk.commit_public(_ATTESTOR))
    return _ATTESTOR


def new_task(goal, function=None, cases=None):
    tid = uuid.uuid4().hex[:10]
    rec = {"id": tid, "goal": goal, "status": "queued",
           "name": function or DEFAULT_FUNCTION,
           "cases": cases or DEFAULT_CASES, "stages": [],
           "artifact": None, "verdict": None, "attestation": None,
           "created": time.strftime("%H:%M:%S"), "duration_ms": 0}
    TASKS[tid] = rec
    telemetry.emit(tid, "info", "هدف ولد → بناء/نقد/إصلاح مع ختم ZK")
    threading.Thread(target=_run, args=(tid,), daemon=True).start()
    return {"id": tid, "status": rec["status"], "name": rec["name"]}


def get(tid):
    with _TLOCK:
        rec = TASKS.get(tid)
        if not rec:
            return None
    out = {k: rec.get(k) for k in ("id", "goal", "status", "name", "stages",
                                   "artifact", "verdict", "attestation",
                                   "created", "duration_ms")}
    return out


def all_tasks(limit=25):
    with _TLOCK:
        items = list(TASKS.values())[::-1][:limit]
    return [{"id": r["id"], "goal": r["goal"], "status": r["status"],
             "verdict": r["verdict"], "attestation": bool(r["attestation"]),
             "name": r["name"]} for r in items]


def _stage(rec, kind, detail=""):
    st = {"kind": kind, "detail": detail[:130], "ok": False, "ms": None}
    rec["stages"].append(st)
    if kind != "heal":
        telemetry.emit(rec["id"], "info", f"{kind}: {detail[:100]}")
    return st


# ---------------- the organism loop ----------------
def _run(tid):
    rec = TASKS[tid]
    try:
        rec["status"] = "running"
        t0 = time.time()
        nodes = [n for n in peers.topology()
                 if n.get("up") and n.get("ollama_url")]
        if not nodes:
            rec["status"] = "failed"
            rec["verdict"] = "no-live-brain"
            telemetry.emit(tid, "error",
                           "بلا عقدة حية بمحرك توليد — مرّرت بصدق كفشل")
            return
        cases = rec.get("cases") or DEFAULT_CASES
        builder_peer = nodes[0]

        stage = _stage(rec, "build", f"builder → {builder_peer.get('name')}")
        gen = peers.generate(builder_peer, SYSTEM_BUILDER,
                             f"{rec['goal']}\nاسم الدالة المطلوب: "
                             f"{rec['name']}", expect_code=True)
        stage["ms"] = gen.get("latency_ms")
        if not gen["ok"] or not gen["text"]:
            rec["status"] = "failed"
            rec["verdict"] = "builder-failed"
            stage["detail"] = (gen.get("error") or "empty output")[:160]
            telemetry.emit(tid, "error", "builder فشل — الحد مضبوط بلا حلقة")
            return
        code = gen["text"]
        stage["ok"] = True

        rep = verify.verify_candidate(code, rec["name"], cases)
        vstage = _stage(rec, "verify", f"sandbox → {rep['verdict']}")
        vstage["ms"] = rep["run"].get("ms")

        heals = 0
        while rep["verdict"] != "clean-pass" and heals < 2:
            heals += 1
            hstage = _stage(rec, "heal", f"healer #{heals}")
            prompt = ("الهدف: " + rec["goal"] + "\nالكود الفاشل:\n" +
                      code[:1800] + "\nأعد إصدار الدالة كاملة بايثون فقط.")
            fix = peers.generate(builder_peer, SYSTEM_HEALER, prompt, timeout=90)
            if fix["ok"] and fix["text"]:
                code = fix["text"]
                hstage["ok"] = True
            else:
                hstage["detail"] = (fix.get("error") or "no output")[:120]
                break
            rep = verify.verify_candidate(code, rec["name"], cases)
            hstage["detail"] = f"re-verify → {rep['verdict']}"

        cstage = _stage(rec, "critic",
                        f"static {rep['static_count']} · tests "
                        f"{rep['run'].get('passed', 0)}/"
                        f"{rep['run'].get('cases', len(cases))} → "
                        f"{rep['verdict']}")
        cstage["ok"] = rep["verdict"] == "clean-pass"

        sha = rep["code_sha256"]
        key = attestor()
        context = zk.context_for(sha, "verdict", "hyperion-core")
        proof = zk.prove(key, context)
        okz = zk.verify(proof, context)
        rec["verdict"] = rep["verdict"]
        rec["attestation"] = {
            "label": f"task-{tid}", "payload_sha256": sha,
            "protocol": zk.protocol_shape()["protocol"], "zk_ok": okz}
        if okz:
            aid = storage.add_attestation(f"task-{tid}", rec["name"],
                                          rep["verdict"], sha, proof)
            rec["attestation"]["aid"] = aid
        storage.lineage_append("verdict-attestation",
                               f"task-{tid} {rec['name']} {rep['verdict']}",
                               sha)
        telemetry.emit(tid, "ok" if rep["verdict"] == "clean-pass" else "warn",
                       f"عقد القرار: {rep['verdict']} · zk "
                       f"{'✓' if okz else '✗'}")

        art_dir = config.ARTIFACTS / tid
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / f"{rec['name']}.py").write_text(code, encoding="utf-8")
        (art_dir / "verdict.json").write_text(json.dumps(
            {"verdict": rep["verdict"], "code_sha256": sha,
             "attestation": rec["attestation"], "repair_attempts": heals},
            ensure_ascii=False, indent=1), encoding="utf-8")
        rec["artifact"] = str(art_dir)
        rec["status"] = "done"
        rec["duration_ms"] = int((time.time() - t0) * 1000)
        storage.log_event(tid, "info", f"duration_ms={rec['duration_ms']}")
    except Exception as e:
        rec["status"] = "failed"
        telemetry.emit(tid, "error", f"استثناء: {type(e).__name__}: {e}"[:200])
