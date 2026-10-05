"""Deterministic, bounded retrieval of project engineering evidence.

The retriever intentionally uses lexical overlap instead of opaque model judgment.
It is designed to be predictable, inspectable, and safe for prompt construction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "to", "with", "this", "these",
    "those", "into", "than", "then", "their", "them", "there", "here", "use", "using",
}
_TOKEN_RE = re.compile(r"[a-z0-9_./#-]{2,}")


@dataclass(frozen=True)
class RetrievedEvidence:
    kind: str
    record_id: str
    score: int
    reason: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RetrievalPacket:
    query: str
    items: tuple[RetrievedEvidence, ...]
    context_text: str


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _score(query_tokens: set[str], text: str) -> int:
    if not query_tokens:
        return 0
    candidate = _tokens(text)
    overlap = len(query_tokens & candidate)
    if not overlap:
        return 0
    # Favor direct overlap while avoiding huge advantages from long records.
    return min(100, round(100 * overlap / max(1, len(query_tokens))))


def _task_text(task: Any) -> str:
    status = getattr(task, "status", "")
    if hasattr(status, "value"):
        status = status.value
    prompt = " ".join(str(getattr(task, "prompt", "") or "").split())
    answer = " ".join(str(getattr(task, "answer", "") or "").split())[:160]
    error = " ".join(str(getattr(task, "error", "") or "").split())[:160]
    return f"{prompt} {status} {answer} {error}".strip()


def retrieve_project_evidence(
    query: str,
    tasks: Iterable[Any] = (),
    learnings: Iterable[dict[str, Any]] = (),
    *,
    max_items: int = 6,
    min_score: int = 15,
) -> RetrievalPacket:
    clean_query = " ".join(query.strip().split())[:4000]
    qtokens = _tokens(clean_query)
    candidates: list[RetrievedEvidence] = []

    for task in tasks:
        task_id = str(getattr(task, "task_id", ""))
        prompt_text = " ".join(str(getattr(task, "prompt", "") or "").split())[:1200]
        outcome_text = " ".join(str(getattr(task, "answer", "") or "").split())[:160]
        error_text = " ".join(str(getattr(task, "error", "") or "").split())[:160]
        text = prompt_text
        score = _score(qtokens, text)
        # Small evidence bonus when an otherwise relevant task outcome/error shares query terms.
        if score and (outcome_text or error_text):
            score = min(100, score + round(_score(qtokens, outcome_text + " " + error_text) * 0.15))
        if score < min_score or not task_id:
            continue
        status = getattr(task, "status", "")
        if hasattr(status, "value"):
            status = status.value
        prompt = " ".join(str(getattr(task, "prompt", "") or "").split())[:220]
        candidates.append(
            RetrievedEvidence(
                kind="task",
                record_id=task_id,
                score=score,
                reason=f"{score}% query-token overlap with task prompt/outcome",
                text=f"task={task_id} status={status} prompt={prompt}",
                metadata={"status": str(status), "steps": int(getattr(task, "steps", 0) or 0)},
            )
        )

    for item in learnings:
        learning_id = str(item.get("id", ""))
        lesson = " ".join(str(item.get("lesson", "") or "").split())[:280]
        evidence = " ".join(str(item.get("evidence", "") or "").split())[:180]
        text = f"{lesson} {evidence} {item.get('category', '')}"
        score = _score(qtokens, text)
        if score < min_score or not learning_id:
            continue
        candidates.append(
            RetrievedEvidence(
                kind="learning",
                record_id=learning_id,
                score=score,
                reason=f"{score}% query-token overlap with verified lesson/evidence",
                text=f"lesson[{item.get('category', 'general')}]: {lesson}",
                metadata={"category": item.get("category", "general"), "score": int(item.get("score", 0) or 0)},
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.kind, item.record_id))
    items = tuple(candidates[: max(1, min(max_items, 20))])
    if items:
        lines = [f"[retrieved_context query={clean_query[:240] if clean_query else '(empty)'}]"]
        lines.extend(f"- {item.kind}:{item.record_id} score={item.score} {item.text}" for item in items)
        context = "\n".join(lines)
    else:
        context = "[retrieved_context]\nNo relevant persisted project evidence met the retrieval threshold."
    return RetrievalPacket(query=clean_query, items=items, context_text=context)
