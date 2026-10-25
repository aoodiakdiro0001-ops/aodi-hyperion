"""Aodı-Hyperion — REAL zero-knowledge attestation layer (stdlib, pure math).

Schnorr proof of knowledge of a discrete log (Sigma protocol), made
non-interactive via the Fiat–Shamir transform over sha256:

    group: RFC 3526 "Group 14" 2048-bit MODP prime, generator g=2
    keygen:  x ← [1, p-2];        y = g^x mod p
    prove:   k ← [1, p-2];        r = g^k
             c = H(y || r || context) mod (p-1)
             s = (k + c·x) mod (p-1)
    verify:  g^s ≟ (r · y^c) mod p

Honest scope: this is a complete + sound + honest-verifier zero-knowledge
proof of identity/attestor knowledge binding a payload hash — a real ZK
protocol, NOT a general-purpose SNARK compiler (which would violate the
stdlib-only discipline). Everything stays on your machine.
"""
import hashlib, secrets

# RFC 3526 §3 (Group 14, 2048 bits) — exact modulus.
_P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74"
    "020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F1437"
    "4FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF05"
    "98DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB"
    "9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF695581718"
    "3995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
_G = 2
_Q = (_P - 1) // 2


def _h(*parts):
    digest = hashlib.sha256(b"".join(part if isinstance(part, bytes)
                                     else str(part).encode()
                                     for part in parts)).digest()
    return int.from_bytes(digest, "big") % _Q


def keygen():
    """Attestor identity: secret x, public y."""
    x = secrets.randbelow(_Q - 1) + 1
    y = pow(_G, x, _P)
    return {"x": x, "y": y}


def y_hex(y):
    return format(y, "x")


def commit_public(key):
    return y_hex(key["y"])


def prove(key, context):
    """ZK proof binding `context` (usually sha256 of an artifact) to key.x."""
    k = secrets.randbelow(_Q - 1) + 1
    r = pow(_G, k, _P)
    ctx = context if isinstance(context, bytes) else context.encode()
    c = _h(y_hex(key["y"]).encode(), format(r, "x").encode(), ctx)
    s = (k + c * key["x"]) % _Q
    return {"y": y_hex(key["y"]), "r": format(r, "x"),
            "c": format(c, "x"), "s": format(s, "x")}


def verify(proof, context):
    """True iff the proof binds `context` to knowledge of x for public y."""
    try:
        y = int(proof["y"], 16)
        r = int(proof["r"], 16)
        c = int(proof["c"], 16)
        s = int(proof["s"], 16)
        if not (2 <= y < _P) or not (1 <= s < _Q):
            return False
        ctx = context if isinstance(context, bytes) else context.encode()
        expect = _h(format(y, "x").encode(), format(r, "x").encode(), ctx)
        if expect != c:
            return False
        lhs = pow(_G, s, _P)
        rhs = (r * pow(y, c, _P)) % _P
        return lhs == rhs
    except (KeyError, ValueError, TypeError):
        return False


def context_for(payload_sha256, kind, owner):
    return f"{kind}:{owner}:{payload_sha256}"


# ---------- self-test of the protocol soundness (fast, small subgroup) ----
def protocol_shape():
    """Human-readable shape (no secrets) for dashboards."""
    return {"protocol": "schnorr-sigma (Fiat–Shamir over sha256)",
            "group": "RFC 3526 modp 2048-bit", "generator": _G,
            "bits": _P.bit_length(), "soundness": "discrete-log"}


if __name__ == "__main__":
    import time
    key = keygen()
    ctx = context_for("deadbeef" * 8, "artifact-verify", "hyperion-core")
    t0 = time.perf_counter()
    pf = prove(key, ctx)
    t1 = time.perf_counter()
    ok = verify(pf, ctx)
    t2 = time.perf_counter()
    bad = verify(pf, ctx + "x")
    import sys
    print("prove %.1fms verify %.1fms ok=%s foreign-ctx=%s"
          % ((t1 - t0) * 1e3, (t2 - t1) * 1e3, ok, bad))
    sys.exit(0 if (ok and not bad) else 1)
