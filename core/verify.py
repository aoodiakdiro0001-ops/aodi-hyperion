"""Aodı-Hyperion — bounded verification sandbox + property checks.

Every candidate walks: syntax → isolated `python -I` execution with rlimits →
golden property tests → static heuristics (forbidden patterns). Verdicts are
sealed by zk attestations downstream. Bounded, honest, zero cloud.
"""
import json, os, re, signal, subprocess, sys, tempfile, time
from pathlib import Path

import config

FORBIDDEN = [
    ("HY-D01", re.compile(r"(?<![\w.])eval\s*\("), "dynamic eval call"),
    ("HY-D02", re.compile(r"(?<![\w.])exec\s*\("), "dynamic exec call"),
    ("HY-D03", re.compile(r"__import__\s*\("), "dynamic import"),
    ("HY-D04", re.compile(r"subprocess|os\.(system|popen)"), "shell escape"),
    ("HY-D05", re.compile(r"while\s+True\s*:"), "unbounded loop"),
    ("HY-D06", re.compile(r"(pickle|marshal)\.loads?\s*\("), "unsafe deserialize"),
    ("HY-D07", re.compile(r"(?i)(password|token|secret)\s*=\s*[\"'][^\"']{8,}"),
     "hardcoded secret literal"),
]


def static_findings(code):
    out = []
    for i, line in enumerate(code.splitlines(), 1):
        for rid, rx, msg in FORBIDDEN:
            if rx.search(line):
                out.append({"line": i, "rule": rid, "message": msg,
                            "snippet": line.strip()[:120]})
    return out


def _prep():
    def apply():
        mem = config.SANDBOX_MEM_MB * 1024 * 1024
        for res, lim in ((18, (mem, mem)),      # RLIMIT_AS
                         (4, (0, 0)),           # RLIMIT_CORE
                         (6, (24, 24))):        # RLIMIT_NPROC
            try:
                import resource
                resource.setrlimit(res, lim)
            except Exception:
                pass
        try:
            import resource
            c = config.SANDBOX_TIMEOUT
            resource.setrlimit(resource.RLIMIT_CPU, (c, c + 2))
        except Exception:
            pass
    return apply


def run_candidate(code, function, cases):
    """cases: list of (args_tuple, expected) — executed inside an isolated
    child (python -I) against a probe harness. Honest verdicts only."""
    import signal as _sig
    def expectation_key(v):
        return json.dumps(v, sort_keys=True, default=str)
    with tempfile.TemporaryDirectory(prefix="hy_verify_") as d:
        runner = os.path.join(d, "runner.py")
        probe = os.path.join(d, "probe.json")
        payload = code + """

import json, sys
probe = json.load(open(sys.argv[1], encoding="utf-8"))
cases = probe["cases"]
fname = probe["function"]
fn = globals().get(fname)
out = []
if fn is None:
    out.append({"ok": False, "error": "function missing"})
else:
    for case in cases:
        try:
            got = fn(*case[0])
            out.append({"ok": True, "got": got})
        except Exception as e:
            out.append({"ok": False, "error": type(e).__name__ + ": " + str(e)[:120]})
print("HY_VERIFY:" + json.dumps(out))
"""
        Path(runner).write_text(payload, encoding="utf-8")
        Path(probe).write_text(json.dumps({
            "function": function,
            "cases": [[list(a), expectation_key(e)] for a, e in cases]},
            default=str), encoding="utf-8")
        t0 = time.time()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", runner, probe], cwd=d,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                preexec_fn=_prep(), start_new_session=True)
            out, _ = proc.communicate(timeout=config.SANDBOX_TIMEOUT)
            dur = int((time.time() - t0) * 1000)
            txt = out.decode("utf-8", "replace")[-4000:]
            if proc.returncode != 0:
                return {"ok": False, "verdict": "crash", "ms": dur,
                        "error": txt[-300:]}
            marker = txt.rfind("HY_VERIFY:")
            if marker < 0:
                return {"ok": False, "verdict": "no-marker", "ms": dur,
                        "error": "harness did not report"}
            results = json.loads(txt[marker + 10:].splitlines()[0] or "[]")
            passed = []
            for (args, expected), got in zip(cases, results):
                exp = expectation_key(expected)
                if got.get("ok") and json.dumps(got.get("got"), sort_keys=True,
                                                default=str) == exp:
                    passed.append(True)
                else:
                    passed.append(False)
            score = sum(passed) / len(passed) if passed else 0.0
            return {"ok": score == 1.0, "verdict": "pass" if score == 1.0
                    else "partial", "score": round(score, 3), "ms": dur,
                    "cases": len(cases), "passed": sum(passed),
                    "detail": [{"ok": p, "type": r.get("error", "ok")}
                               for p, r in zip(passed, results)]}
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            return {"ok": False, "verdict": "timeout", "ms": int((time.time() - t0) * 1000)}


def verify_candidate(code, function, cases):
    """Full verification: static heuristics + sandbox properties."""
    findings = static_findings(code)
    run = run_candidate(code, function, cases)
    verdict = "clean-pass" if run.get("ok") and not findings else (
        "partial" if run.get("score", 0) > 0 else "reject")
    return {"function": function, "code_sha256": __import__("hashlib")
            .sha256(code.encode()).hexdigest(), "static": findings,
            "static_count": len(findings), "run": run, "verdict": verdict}
