"""Small numeric and text helpers shared by the engines."""

from __future__ import annotations

import math
import re

from rank_bm25 import BM25Okapi


class EngineError(ValueError):
    """Raised when an engine receives invalid input. The message is shown to agents and users."""


def r2(value: float) -> float:
    """Round money and quantities to 2 decimals at output (avoids -0.0)."""
    return round(value, 2) + 0.0


def ceil_tol(value: float) -> int:
    """Ceiling with a small tolerance: round to 6 decimals first, so 5.0000000001 gives 5."""
    return math.ceil(round(value, 6))


_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase tokens; keeps codes such as `b-04-010` and `13.3` whole; strips a plural `s`."""
    tokens = []
    for tok in _TOKEN.findall(text.lower()):
        if len(tok) > 3 and tok.endswith("s") and tok.isalpha():
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


def bm25_scores(documents: list[str], query: str) -> list[float]:
    """BM25 score of the query against each document (same order as `documents`)."""
    corpus = [tokenize(d) for d in documents]
    query_tokens = tokenize(query)
    if not query_tokens:
        return [0.0] * len(documents)
    return [float(s) for s in BM25Okapi(corpus).get_scores(query_tokens)]
