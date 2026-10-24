"""BOQ engine: search the bill of quantities and read single lines."""

from __future__ import annotations

from pydantic import BaseModel

from pvr.engines.common import EngineError, bm25_scores, tokenize
from pvr.models import BoqItem, ProjectData


class BoqHit(BaseModel):
    code: str
    bill_name: str
    description: str
    unit: str
    quantity: float
    rate_aed: float
    lump_sum: bool
    score: float
    exact_code_match: bool


def _hit(item: BoqItem, score: float, exact: bool) -> BoqHit:
    return BoqHit(
        code=item.code, bill_name=item.bill_name, description=item.description, unit=item.unit,
        quantity=item.quantity, rate_aed=item.rate_aed, lump_sum=item.lump_sum,
        score=round(score, 4), exact_code_match=exact,
    )


def search_boq(query: str, data: ProjectData, top_k: int = 5) -> list[BoqHit]:
    """BM25 over code + bill name + description. Lines whose code appears in the query rank first."""
    if top_k < 1:
        raise EngineError("top_k must be at least 1")
    query_tokens = set(tokenize(query))
    scores = bm25_scores([f"{i.code} {i.bill_name} {i.description}" for i in data.boq], query)
    exact = [i for i in data.boq if i.code.lower() in query_tokens]
    exact_codes = {i.code for i in exact}
    ranked = sorted(
        (pair for pair in zip(data.boq, scores) if pair[1] > 0 and pair[0].code not in exact_codes),
        key=lambda pair: -pair[1],
    )
    by_code = dict(zip((i.code for i in data.boq), scores))
    hits = [_hit(i, by_code[i.code], True) for i in exact] + [_hit(i, s, False) for i, s in ranked]
    return hits[:top_k]


def get_boq_item(code: str, data: ProjectData) -> BoqItem:
    """One BOQ line by exact code."""
    try:
        return data.boq_item(code.strip().upper())
    except KeyError:
        raise EngineError(f"Unknown BOQ code: {code}") from None
