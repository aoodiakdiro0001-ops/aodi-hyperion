"""Aodı-Hyperion — heterogenous tensor sharding (real block-parallel matmul).

Splits C = A*B into K*K blocks; each block's rows/cols are summed by
**different workers** (remote HTTP workers or injected functions), then the
organism reduces them locally. Honest scope: this shards *numerical tensor
math* across the fleet — it does NOT partition LLM weights (that needs a
different executor ecosystem and is documented as future work, not faked).
"""
import time

import config


def block_matmul(A, B, r0, r1, c0, c1):
    """Partial C[r0:r1, c0:c1] = A[r0:r1,:] · B[:,c0:c1] (pure python)."""
    inner = len(B)
    out = []
    for i in range(r0, r1):
        row = []
        for j in range(c0, c1):
            s = 0.0
            for k in range(inner):
                s += A[i][k] * B[k][j]
            row.append(s)
        out.append(row)
    return out


def split_matrix(A, K):
    n = len(A)
    step = (n + K - 1) // K
    spans = []
    for a in range(0, n, step):
        spans.append((a, min(a + step, n)))
    return spans


def shard_matmul(A, B, workers, K=2):
    """workers: list of callables (name, A, B, r0, r1, c0, c1) or HTTP urls.

    Returns {"ok", "C", "blocks", "ms", "per_worker"} — each block's compute
    happens in exactly one worker; failures bubble up honestly (no silent
    local fallback re-computation, ever).
    """
    n, inner, m = len(A), len(B), len(B[0])
    if not workers:
        workers = [block_matmul]
    rows = split_matrix(A, K)
    cols = split_matrix(B, K)
    import urllib.request, json as _json

    def call(name, A, B, r0, r1, c0, c1):
        if callable(name):
            return name(A, B, r0, r1, c0, c1)
        payload = _json.dumps({"A": A, "B": B, "r0": r0, "r1": r1,
                               "c0": c0, "c1": c1}).encode("utf-8")
        req = urllib.request.Request(
            name, data=payload, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=config.TENSOR_BLOCKS_TIMEOUT) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    C = [[0.0] * m for _ in range(n)]
    per = {}
    t0 = time.perf_counter()
    jobs = [(ri, ci) for ri, (r0, r1) in enumerate(rows)
            for ci, (c0, c1) in enumerate(cols)]
    for idx, (ri, ci) in enumerate(jobs):
        worker = workers[idx % len(workers)]
        r0, r1 = rows[ri]
        c0, c1 = cols[ci]
        blk = call(worker, A, B, r0, r1, c0, c1)
        for i, rowv in enumerate(blk):
            C[r0 + i][c0:c1] = rowv
        name = getattr(worker, "__name__", str(worker)[:40])
        per[name] = per.get(name, 0) + 1
    return {"ok": True, "C": C, "blocks": len(jobs),
            "ms": int((time.perf_counter() - t0) * 1000), "per_worker": per}


# deterministic local reference (verifier of distributed result)
def ref_matmul(A, B):
    return block_matmul(A, B, 0, len(A), 0, len(B[0]))


def random_matrix(n, rng=None):
    import random
    rng = rng or random.Random(1969)
    return [[rng.random() for _ in range(n)] for _ in range(n)]


def close(C, R, eps=1e-9):
    for i, row in enumerate(C):
        for j, v in enumerate(row):
            if abs(v - R[i][j]) > max(eps, abs(R[i][j]) * eps * 8):
                return False
    return True
