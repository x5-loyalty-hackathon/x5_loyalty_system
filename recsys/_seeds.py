"""Reproducible seeds from arbitrary parts, including strings.

Lives in its own module because both ``recsys.benchmark`` and
``recsys.true_pantry`` need it and importing one from the other is a cycle.
"""

from __future__ import annotations

import zlib


def stable_seed(*parts: object) -> int:
    """Deterministic across processes and machines, unlike ``hash()``.

    ``hash()`` is randomised per process for str and bytes (PYTHONHASHSEED), so
    seeding an RNG from ``hash((seed, "rule_based"))`` silently produces a
    different stream on every run. Two sweeps with identical arguments then
    disagree, which is exactly what happened here before this existed: a claim
    about the bench flipped between two runs that should have been identical.
    """
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return zlib.crc32(payload)
