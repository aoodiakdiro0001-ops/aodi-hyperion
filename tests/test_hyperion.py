"""Aodı-Hyperion — offline tests: zk · genetic engine · tensor sharding ·
verification sandbox · lineage chain. All state isolated to a temp HY_HOME.
"""
import os, sys, tempfile, unittest
from pathlib import Path

# كل اختبار يعزل حالته في دليل مؤقت — لا يلمس قاعدة ~/.hyperion الحقيقية أبداً
os.environ["HY_HOME"] = tempfile.mkdtemp(prefix="hy_test_")

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import zk            # noqa: E402
import storage       # noqa: E402
import evolve        # noqa: E402
import tensor        # noqa: E402
import verify        # noqa: E402
import config        # noqa: E402


class ZKTests(unittest.TestCase):
    def test_prove_verify_roundtrip(self):
        key = zk.keygen()
        ctx = zk.context_for("deadbeef" * 4, "verdict", "core")
        proof = zk.prove(key, ctx)
        self.assertTrue(zk.verify(proof, ctx))
        # soundness: different context must fail
        self.assertFalse(zk.verify(proof, ctx + "x"))
        # forgery: mutate s
        forged = dict(proof)
        forged["s"] = format((int(proof["s"], 16) ^ 1), "x")
        self.assertFalse(zk.verify(forged, ctx))

    def test_public_key_never_reveals_secret(self):
        import json
        key = zk.keygen()
        ctx = zk.context_for("aabbccdd" * 8, "attest", "core")
        proof = zk.prove(key, ctx)
        blob = json.dumps(proof)
        self.assertNotIn(str(key["x"]), blob)

    def test_protocol_shape(self):
        s = zk.protocol_shape()
        self.assertEqual(s["bits"], 2048)
        self.assertIn("schnorr", s["protocol"])


class LineageTests(unittest.TestCase):
    def test_append_and_verify(self):
        e1 = storage.lineage_append("t-kind", "label-1", "sha-a")
        e2 = storage.lineage_append("t-kind", "label-2", "sha-b")
        self.assertEqual(e2["prev_hash"], e1["hash"])
        v = storage.verify_lineage()
        self.assertTrue(v["ok"], v)
        with storage._LOCK:
            storage._db().execute(
                "UPDATE lineage SET payload_sha256='deadbeef' WHERE idx=?",
                (e1["idx"],))
            storage._db().commit()
        v2 = storage.verify_lineage()
        self.assertFalse(v2["ok"])
        self.assertEqual(v2["broken_at_idx"], e1["idx"])

    def test_attestations_crud(self):
        key = zk.keygen()
        proof = zk.prove(key, zk.context_for("c0ffee" * 8, "attest", "c"))
        aid = storage.add_attestation("lbl", None, "sealed", "c0ffee" * 8,
                                      proof)
        rows = storage.list_attestations()
        self.assertTrue(any(r["aid"] == aid for r in rows))


class EvolveTests(unittest.TestCase):
    def test_reaches_reference_fitness(self):
        import random
        rep = evolve.evolve_population(generations=2, population=4,
                                       rng=random.Random(11))
        self.assertTrue(rep["ok"])
        self.assertGreaterEqual(rep["best_fitness"], 0.99)
        self.assertEqual(rep["history"][-1]["gen"], 2)
        self.assertIn("verdict", rep["history"][0])

    def test_lineage_seals_each_generation(self):
        import random
        before = storage.verify_lineage()["size"]
        evolve.evolve_population(generations=1, population=3,
                                 rng=random.Random(5))
        after = storage.verify_lineage()["size"]
        self.assertEqual(after - before, 1)

    def test_seed_baseline_is_truth(self):
        fit, rep = evolve.fitness_of(evolve.BASE_SEED)
        self.assertEqual(rep["verdict"], "clean-pass", rep)
        self.assertEqual(fit, 1.0)


class TensorTests(unittest.TestCase):
    def test_sharded_matches_reference(self):
        A = tensor.random_matrix(9)
        B = tensor.random_matrix(9)
        workers = [tensor.block_matmul, tensor.block_matmul]
        out = tensor.shard_matmul(A, B, workers, K=3)
        ref = tensor.ref_matmul(A, B)
        self.assertTrue(tensor.close(out["C"], ref))
        self.assertEqual(out["blocks"], 9)

    def test_two_remote_machines_share_load(self):
        counts = {"a": 0, "b": 0}
        def wa(*args):
            counts["a"] += 1
            return tensor.block_matmul(*args)
        def wb(*args):
            counts["b"] += 1
            return tensor.block_matmul(*args)
        A = tensor.random_matrix(6)
        B = tensor.random_matrix(6)
        tensor.shard_matmul(A, B, [wa, wb], K=2)
        self.assertGreater(counts["a"], 0)
        self.assertGreater(counts["b"], 0)
        self.assertEqual(counts["a"] + counts["b"], 4)


class VerifyTests(unittest.TestCase):
    def test_clean_code_passes(self):
        code = ("def order_dedup(items):\n"
                "    seen, out = set(), []\n"
                "    for x in items:\n"
                "        if x not in seen:\n"
                "            seen.add(x)\n"
                "            out.append(x)\n"
                "    return out\n")
        rep = verify.verify_candidate(code, "order_dedup",
                                      evolve.CASES[:3])
        self.assertEqual(rep["verdict"], "clean-pass", rep)
        self.assertEqual(rep["static_count"], 0)

    def test_eval_is_caught(self):
        code = 'def order_dedup(items):\n    return eval(items)\n'
        rep = verify.verify_candidate(code, "order_dedup",
                                      evolve.CASES[:2])
        self.assertEqual(rep["verdict"], "reject")
        self.assertIn("HY-D01", [f["rule"] for f in rep["static"]])

    def test_crashing_code_never_counts_as_pass(self):
        code = ("def order_dedup(items):\n"
                "    return [x for x in items] / 0\n")
        rep = verify.verify_candidate(code, "order_dedup",
                                      evolve.CASES[:2])
        self.assertEqual(rep["verdict"], "reject")


class ConfigTests(unittest.TestCase):
    def test_home_isolated(self):
        self.assertNotIn(str(Path.home()), str(config.HOME))


if __name__ == "__main__":
    unittest.main(verbosity=2)
