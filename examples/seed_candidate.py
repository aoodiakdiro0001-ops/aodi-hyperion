#!/usr/bin/env python3
"""Aodı-Hyperion — a deliberately broken seed for sandbox-propert nature demos.

Property cases run against `order_dedup` behave honestly: this file is a
reference of a *failing* candidate (repr output, reversed traversal, eval) —
the organism's verifier must give it a low score, never a pass.
"""


def order_dedup(items):
    """would-be genome that violates the properties it promises"""
    seen = []
    out = []
    for x in reversed(items):
        if x not in seen:
            seen.append(x)
            out.append(repr(x))
    return out
