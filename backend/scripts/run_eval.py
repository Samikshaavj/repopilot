import json
import sys
from functools import partial
from pathlib import Path

from app.db import get_connection
from app.search import hybrid_search, keyword_search, vector_search

EVAL_DIR = Path(__file__).resolve().parent.parent / "evals"
K = 5

def weighted(keyword_weight: float):
    """A hybrid search where keyword results count `keyword_weight` times as much."""
    return partial(
        hybrid_search,
        weights={"vector": 1.0, "keyword": keyword_weight, "name": 1.0},
    )


METHODS = {
    "vector": vector_search,
    "keyword": keyword_search,
    "hyb 1.0": weighted(1.0),
    "hyb 0.5": weighted(0.5),
    "hyb 0.25": weighted(0.25),
    "hyb 0.0": weighted(0.0),
        "default": hybrid_search,
}


def get_repo_id(url: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM repositories WHERE url = %s AND status = 'ready'", (url,)
        ).fetchone()
    if row is None:
        sys.exit(f"{url} is not indexed. Run scripts.index_repo first.")
    return row[0]


def known_names(repo_id: int) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT qualified_name FROM chunks WHERE repo_id = %s", (repo_id,)
        ).fetchall()
    return {r[0] for r in rows}


def rank_of_first_hit(method, repo_id: int, item: dict):
    """Position (1-5) of the first correct result, or None for a miss."""
    expected = set(item["expected"])
    results = method(repo_id, item["q"], limit=K)
    for position, result in enumerate(results, start=1):
        if result.qualified_name in expected:
            return position
    return None


def main(name: str) -> None:
    data = json.loads((EVAL_DIR / f"{name}.json").read_text(encoding="utf-8"))
    repo_id = get_repo_id(data["repo"])
    names = known_names(repo_id)

    questions = []
    for item in data["questions"]:
        missing = [n for n in item["expected"] if n not in names]
        if missing:
            print(f"WARNING not in index: {missing}  <- question: {item['q']}")
        if len(missing) == len(item["expected"]):
            print("  skipping this question; fix its expected names\n")
            continue
        questions.append(item)

    ranks = {m: [] for m in METHODS}
    print(f"\n{'question':<52}" + "".join(f"{m:>9}" for m in METHODS))
    for item in questions:
        row = f"{item['q'][:50]:<52}"
        for m, method in METHODS.items():
            rank = rank_of_first_hit(method, repo_id, item)
            ranks[m].append(rank)
            row += f"{('#' + str(rank)) if rank else 'miss':>9}"
        print(row)

    total = len(questions)
    print(f"\nScores over {total} questions (top {K}):")
    for m, values in ranks.items():
        hits = sum(1 for r in values if r)
        mrr = sum(1 / r for r in values if r) / total
        print(f"  {m:<8} hit@{K} = {hits / total:.0%}   MRR = {mrr:.3f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "itsdangerous")