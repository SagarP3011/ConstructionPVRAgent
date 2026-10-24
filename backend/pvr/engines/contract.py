"""Contract engine: clause search, clause lookup and the notice period check."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from pvr.engines.common import EngineError, bm25_scores, tokenize
from pvr.models import Clause, ProjectData


class ClauseHit(BaseModel):
    clause: str
    title: str
    text: str
    score: float


class NoticeCheck(BaseModel):
    event_date: date
    notice_date: date
    calendar_days: int
    limit_days: int
    within_limit: bool
    clause: str


def search_contract(query: str, data: ProjectData, top_k: int = 3) -> list[ClauseHit]:
    """BM25 over clause title and text. A clause number in the query ranks that clause first."""
    if top_k < 1:
        raise EngineError("top_k must be at least 1")
    clauses = data.contract.clauses
    query_tokens = set(tokenize(query))
    scores = bm25_scores([f"{c.title} {c.text}" for c in clauses], query)
    ranked = sorted(
        ((c, s) for c, s in zip(clauses, scores) if s > 0 or c.clause in query_tokens),
        key=lambda pair: (pair[0].clause not in query_tokens, -pair[1]),
    )
    return [ClauseHit(clause=c.clause, title=c.title, text=c.text, score=round(s, 4)) for c, s in ranked[:top_k]]


def get_clause(clause_id: str, data: ProjectData) -> Clause:
    """One clause by number, for example `13.3`."""
    wanted = clause_id.strip().removeprefix("Clause").strip()
    for c in data.contract.clauses:
        if c.clause == wanted:
            return c
    raise EngineError(f"Unknown clause: {clause_id}")


def clause_exists(clause_id: str, data: ProjectData) -> bool:
    """True when the clause number exists in the contract."""
    return any(c.clause == clause_id for c in data.contract.clauses)


def check_notice(event_date: date, notice_date: date, limit_days: int = 28, clause: str = "20.1") -> NoticeCheck:
    """Calendar days from the event to the notice, and whether that is within the limit."""
    if notice_date < event_date:
        raise EngineError("Notice date is before the event date")
    if limit_days < 0:
        raise EngineError("limit_days must be zero or more")
    days = (notice_date - event_date).days
    return NoticeCheck(
        event_date=event_date, notice_date=notice_date, calendar_days=days,
        limit_days=limit_days, within_limit=days <= limit_days, clause=clause,
    )
