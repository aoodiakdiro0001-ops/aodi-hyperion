"""Aodı-Hyperion — real genetic engine over executable code genomes.

Genome = actual Python source of one candidate function. Mutation operators
perturb the source text in bounded ways; fitness = isolated sandbox verdict
(property tests inside `python -I` + static heuristics). Weak individuals are
killed; elite pair crossover mixes surviving logic — generation ledgers are
append-only in the lineage chain. Honest scope: this evolves *code candidates
and execution genes* of the organism, not neural-network weights (documented).
"""
import random
import re

import config
import storage
import verify

BASE_SEED = '''def order_dedup(items):
    """Seed genome: preserve order while removing duplicates."""
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
'''

# Property cases used to score EVERY genome (behavioral truth, no LLM)
CASES = [
    ((["a", "b", "a", "c", "b", "d"],), ["a", "b", "c", "d"]),
    (([1, 2, 2, 3, 1],), [1, 2, 3]),
    (([],), []),
    (([3, 3],), [3]),
    (([None, "x", None, "x"],), [None, "x"]),
]

SECTION = re.compile(r"def order_dedup\(items\):\n(?:    .*\n|.*\n)*?return out\n")


def mutate(code, rng):
    """Bounded mutation operators over real code text."""
    kind = rng.choice(("collect-mode", "loop-rewrite", "precheck",
                       "dead-tweak", "spacing"))
    if kind == "collect-mode":
        return code.replace("out.append(x)", rng.choice(
            ["out.insert(0, x)", "out.append(repr(x))", "out.append(x)"]),
            1)
    if kind == "loop-rewrite" and "for x in items:" in code:
        return code.replace("for x in items:",
                            rng.choice(["for x in reversed(items):",
                                        "for x in items:"]))
    if kind == "precheck" and "return out" in code:
        return code.replace("    return out\n",
                            "    return out if out else list(items)\n")
    if kind == "dead-tweak" and "seen = set()" in code:
        return code.replace("seen = set()", "seen = []" if rng.random() < 0.4
                            else "seen = set()")
    if kind == "spacing":
        return code.replace("if x not in seen:", "if x  not in seen:")
    return code


def crossover(code_a, code_b, rng):
    """Elite crossover: keep A's loop, graft B's collection behaviour."""
    graft = ("out.insert(0, x)" if "out.insert(0, x)" in code_b
             else "out.append(x)")
    base = code_a.replace("out.append(x)", graft)
    return base


def fitness_of(genome):
    rep = verify.verify_candidate(genome, "order_dedup", CASES)
    score = (rep["run"].get("score", 0.0) if rep["run"].get("ms") is not None
             else 0.0)
    if rep["static_count"] > 0:
        score = max(0.0, score - 0.5)
    ms = rep["run"].get("ms") or 100000
    speed_bonus = max(0.0, (60 - min(ms, 60)) / 60.0) * 0.05
    fit = round(min(score + speed_bonus, 1.0), 3)
    return fit, rep


def evolve_population(generations=None, population=None, rng=None,
                      use_nodes=False):
    """Real loop: evaluate → kill weakest → crossover elites → mutate."""
    generations = max(1, min(generations or config.MAX_GENERATIONS,
                             config.MAX_GENERATIONS))
    population = max(3, min(population or config.POPULATION, 12))
    rng = rng or random.Random(0x1A0000)
    import uuid
    code0 = BASE_SEED
    boot = fitness_of(code0)
    pop = []
    for _ in range(population):
        for tries in range(config.MUTATION_TRIES):
            kid = mutate(code0, rng)
            if kid != code0:
                break
        else:
            kid = code0
        fit, rep = fitness_of(kid)
        pop.append({"cid": uuid.uuid4().hex[:10], "genome": kid,
                    "fitness": fit, "rep": rep})
    history = []
    for gen_no in range(1, generations + 1):
        gen_fits = [p["fitness"] for p in pop]
        best = max(pop, key=lambda p: p["fitness"])
        elites = sorted(pop, key=lambda p: p["fitness"], reverse=True)[:2]
        keep = max(2, population // 3)
        survivors = sorted(pop, key=lambda p: p["fitness"], reverse=True)[:keep]
        kids = list(survivors) + [{"cid": "seed-" + uuid.uuid4().hex[:6],
                                   "genome": code0, "fitness": boot[0],
                                   "rep": boot[1]}]
        kids = kids[:population]
        while len(kids) < population:
            parent_a, parent_b = rng.sample(elites, 2) if len(elites) > 1 \
                else (elites[0], elites[0])
            kid = crossover(parent_a["genome"], parent_b["genome"], rng)
            if rng.random() < 0.7:
                mutated = mutate(kid, rng)
                kid = mutated if mutated != kid else kid
            fit, rep = fitness_of(kid)
            kids.append({"cid": uuid.uuid4().hex[:10], "genome": kid,
                         "fitness": fit, "rep": rep})
        pop = sorted(kids, key=lambda p: p["fitness"], reverse=True)[:population]
        gen_payload = {
            "gen": gen_no, "population": len(pop),
            "best": pop[0]["fitness"], "avg": round(
                sum(p["fitness"] for p in pop) / len(pop), 3),
            "verdict": pop[0]["rep"]["verdict"],
            "code_sha256": pop[0]["rep"]["code_sha256"],
        }
        label = "gen-%02d best=%.3f verdict=%s" % (gen_no, gen_payload["best"],
                                                   gen_payload["verdict"])
        seal_entry = storage.lineage_append("evolution-generation", label,
                                            gen_payload["code_sha256"])
        for p in pop:
            storage.save_candidate(p["cid"], gen_no, {"sha256":
                                 p["rep"]["code_sha256"], "size_lines":
                                 len(p["genome"].splitlines())},
                                 fitness=p["fitness"],
                                 passed=1 if p["fitness"] >= 1.0 else 0,
                                 ms=p["rep"]["run"].get("ms"),
                                 verdict=p["rep"]["verdict"])
        history.append(gen_payload)
    best = pop[0]
    return {"ok": True, "generations": generations, "population": population,
            "best_fitness": best["fitness"],
            "best_genome_sha256": best["rep"]["code_sha256"],
            "best_verdict": best["rep"]["verdict"],
            "best_ms": best["rep"]["run"].get("ms"),
            "history": history,
            "seed_sha256": boot[1]["code_sha256"],
            "seal_head": seal_entry["hash"][:16]}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import json as _j
    rep = evolve_population(generations=3, population=4)
    print(_j.dumps(rep, ensure_ascii=False, indent=1)[:1200])
