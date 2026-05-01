"""Retrieval eval harness — tracks recall@k and MRR."""
import asyncio
from pathlib import Path

import pytest
import yaml

CASES_FILE = Path(__file__).parent / "cases.yaml"


def load_cases():
    with open(CASES_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


async def _search(query: str, top_k: int = 10):
    from pce.db.session import get_session_factory
    from pce.retrieval.search import hybrid_search

    factory = get_session_factory()
    async with factory() as session:
        return await hybrid_search(query, session, top_k=top_k)


def recall_at_k(results, expected_titles: list[str], k: int) -> float:
    top = results[:k]
    hits = sum(
        1 for et in expected_titles
        if any(et.lower() in (r.title or "").lower() for r in top)
    )
    return hits / len(expected_titles) if expected_titles else 0.0


def mrr(results, expected_titles: list[str]) -> float:
    for rank, r in enumerate(results, start=1):
        if any(et.lower() in (r.title or "").lower() for et in expected_titles):
            return 1.0 / rank
    return 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", load_cases())
async def test_retrieval_case(case):
    query = case["query"]
    expected = case.get("expected_titles", [])

    results = await _search(query, top_k=10)

    r5 = recall_at_k(results, expected, 5)
    r10 = recall_at_k(results, expected, 10)
    mrr_score = mrr(results, expected)

    print(f"\nQuery: {query}")
    print(f"  recall@5={r5:.2f}  recall@10={r10:.2f}  MRR={mrr_score:.2f}")
    print(f"  Top results: {[r.title for r in results[:5]]}")

    # Soft assertion — fail only if nothing is found at all when we expect something
    if expected:
        assert r10 > 0, f"Zero recall@10 for query: {query!r}"
