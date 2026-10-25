"""Aodı-Hyperion — SQLite storage (stdlib sqlite3) + sha256 lineage chain.

    organisms   → one row per swarm identity (public zk key y)
    candidates  → genetic population members with fitness scores
    lineage     → sha256 hash chain of every generation / attestation / seal
    attestations→ zk proofs binding verdicts to attestor identities
    events      → telemetry tail
"""
import hashlib, json, sqlite3, threading, time

import config

_LOCK = threading.Lock()
_CONN = None


def _db():
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(str(config.DB_FILE), check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.executescript("""
        CREATE TABLE IF NOT EXISTS organisms(
            oid TEXT PRIMARY KEY, name TEXT, y TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS candidates(
            cid TEXT PRIMARY KEY, gen INTEGER, genome TEXT,
            fitness REAL, passed INTEGER, ms INTEGER, verdict TEXT,
            ts REAL);
        CREATE TABLE IF NOT EXISTS lineage(
            idx INTEGER PRIMARY KEY, ts REAL, kind TEXT, label TEXT,
            payload_sha256 TEXT, prev_hash TEXT, hash TEXT);
        CREATE TABLE IF NOT EXISTS attestations(
            aid INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT, cid TEXT,
            verdict TEXT, payload_sha256 TEXT, proof TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS events(
            ts REAL, gen TEXT, level TEXT, message TEXT);
        """)
        _CONN.commit()
    return _CONN


# ---------- organisms ----------
def new_organism(oid, name, y):
    with _LOCK:
        _db().execute(
            "INSERT OR REPLACE INTO organisms(oid,name,y,created) VALUES(?,?,?,?)",
            (oid, name, y, time.time()))
        _db().commit()


def get_organism(oid):
    with _LOCK:
        row = _db().execute("SELECT * FROM organisms WHERE oid=?", (oid,)).fetchone()
    if not row:
        return None
    return dict(zip([d[0] for d in _db().execute(
        "SELECT * FROM organisms WHERE oid=? LIMIT 0", (oid,)).description],
        row))


# ---------- candidates (genetic population) ----------
def save_candidate(cid, gen, genome, fitness=None, passed=None, ms=None,
                   verdict=None):
    with _LOCK:
        _db().execute(
            "INSERT OR REPLACE INTO candidates(cid,gen,genome,fitness,passed,"
            "ms,verdict,ts) VALUES(?,?,?,?,?,?,?,?)",
            (cid, gen, json.dumps(genome), fitness, passed, ms, verdict,
             time.time()))
        _db().commit()


def list_generation(gen):
    with _LOCK:
        cur = _db().execute(
            "SELECT cid,gen,genome,fitness,passed,ms,verdict,ts FROM candidates "
            "WHERE gen=? ORDER BY fitness DESC", (gen,))
        cols = [d[0] for d in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            try:
                d["genome"] = json.loads(d.get("genome") or "{}")
            except Exception:
                d["genome"] = {}
            out.append(d)
        return out


def fitness_stats(gen):
    rows = list_generation(gen)
    fit = [r["fitness"] for r in rows if r["fitness"] is not None]
    passed = sum(1 for r in rows if r["passed"])
    return {"count": len(rows), "passed": passed,
            "best": max(fit) if fit else None,
            "avg": round(sum(fit) / len(fit), 2) if fit else None}


# ---------- lineage hash chain ----------
def _sha(*parts):
    h = hashlib.sha256()
    h.update(b"".join(p.encode("utf-8") for p in parts))
    return h.hexdigest()


def lineage_append(kind, label, payload_sha256):
    with _LOCK:
        row = _db().execute("SELECT MAX(idx), hash FROM lineage").fetchone()
        idx = (row[0] or 0) + 1
        prev = row[1] if idx > 1 else "GENESIS"
        h = _sha(prev or "", payload_sha256, kind, label)[:64]
        _db().execute(
            "INSERT INTO lineage(idx,ts,kind,label,payload_sha256,prev_hash,hash) "
            "VALUES(?,?,?,?,?,?,?)",
            (idx, time.time(), kind, label[:160], payload_sha256, prev, h))
        _db().commit()
    return {"idx": idx, "kind": kind, "label": label, "payload_sha256":
            payload_sha256, "prev_hash": prev, "hash": h, "ts": time.time()}


def lineage_rows(limit=50):
    with _LOCK:
        cur = _db().execute(
            "SELECT idx,ts,kind,label,payload_sha256,prev_hash,hash FROM "
            "lineage ORDER BY idx DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def verify_lineage():
    rows = list(reversed(lineage_rows(limit=10_000)))
    prev = "GENESIS"
    for r in rows:
        expect = _sha(prev, r["payload_sha256"], r["kind"], r["label"])
        if expect != r["hash"]:
            return {"ok": False, "broken_at_idx": r["idx"], "size": len(rows)}
        prev = r["hash"]
    return {"ok": True, "broken_at_idx": None, "size": len(rows),
            "head": prev}


# ---------- attestations (zk proofs) ----------
def add_attestation(label, cid, verdict, payload_sha256, proof):
    with _LOCK:
        cur = _db().execute(
            "INSERT INTO attestations(label,cid,verdict,payload_sha256,proof,ts)"
            " VALUES(?,?,?,?,?,?)",
            (label[:160], cid, verdict, payload_sha256,
             json.dumps(proof), time.time()))
        _db().commit()
        return cur.lastrowid


def list_attestations(limit=30):
    with _LOCK:
        cur = _db().execute(
            "SELECT aid,label,cid,verdict,payload_sha256,proof,ts FROM "
            "attestations ORDER BY ts DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            try:
                d["proof"] = json.loads(d.get("proof") or "{}")
            except Exception:
                d["proof"] = {}
            out.append(d)
        return out


# ---------- events ----------
def log_event(gen, level, message):
    with _LOCK:
        _db().execute(
            "INSERT INTO events(ts,gen,level,message) VALUES(?,?,?,?)",
            (time.time(), gen or "", level, message[:400]))
        _db().commit()


def event_tail(limit=40):
    with _LOCK:
        cur = _db().execute(
            "SELECT ts,gen,level,message FROM events ORDER BY ts DESC LIMIT ?",
            (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
