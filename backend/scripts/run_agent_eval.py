import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from app.agent import ask
from app.db import get_connection
from app.search import hybrid_search

EVAL_DIR = Path(__file__).resolve().parent.parent / "evals"
RESULTS_FILE = EVAL_DIR / "results" / "agent_results.jsonl"
PAUSE_BETWEEN_QUESTIONS = 10  # seconds; keeps us under free per-minute limits

# Matches "src/pkg/mod.py:40-72" (answers, search results) and "mod.py, lines 70-141" (read_file)
RANGE = re.compile(r"([\w./-]+\.py)(?::|, lines )(\d+)-(\d+)")
DASHES = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-"})


def find_ranges(text: str) -> list[tuple[str, int, int]]:
    """Every path:start-end mentioned in a text, without duplicates."""
    text = text.translate(DASHES)
    found = [(m.group(1), int(m.group(2)), int(m.group(3))) for m in RANGE.finditer(text)]
    return list(dict.fromkeys(found))


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def get_repo_id(url: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM repositories WHERE url = %s AND status = 'ready'", (url,)
        ).fetchone()
    if row is None:
        raise SystemExit(f"{url} is not indexed. Run scripts.index_repo first.")
    return row[0]


def get_file_lengths(repo_id: int) -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT path, content FROM files WHERE repo_id = %s", (repo_id,)).fetchall()
    return {path: len(content.splitlines()) for path, content in rows}


def get_expected_chunks(repo_id: int, names: list[str]):
    """[(qualified_name, path, start_line, end_line)] for the expected symbols."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT c.qualified_name, f.path, c.start_line, c.end_line
               FROM chunks c JOIN files f ON f.id = c.file_id
               WHERE c.repo_id = %s AND c.qualified_name = ANY(%s)""",
            (repo_id, names),
        ).fetchall()


def resolve_path(path: str, file_lengths: dict[str, int]) -> str | None:
    """Accept 'timed.py' as shorthand for 'src/itsdangerous/timed.py' when it is unambiguous."""
    if path in file_lengths:
        return path
    matches = [p for p in file_lengths if p.endswith("/" + path)]
    return matches[0] if len(matches) == 1 else None


def score_answer(answer: str, steps, expected_chunks, file_lengths) -> dict:
    cited = []
    for path, start, end in find_ranges(answer):
        cited.append((resolve_path(path, file_lengths) or path, start, end))
    cited = list(dict.fromkeys(cited))

    seen = []
    for step in steps:
        seen.extend(find_ranges(step.result))

    real = [c for c in cited if c[0] in file_lengths and 1 <= c[1] <= c[2] <= file_lengths[c[0]]]
    grounded = [
        c for c in real
        if any(c[0] == s[0] and overlaps(c[1], c[2], s[1], s[2]) for s in seen)
    ]
    found = any(
        c[0] == path and overlaps(c[1], c[2], start, end)
        for c in cited
        for _, path, start, end in expected_chunks
    )
    return {"cited": len(cited), "real": len(real), "seen": len(grounded), "found": found}


def search_rank(repo_id: int, question: str, expected: set[str]) -> int | None:
    for position, result in enumerate(hybrid_search(repo_id, question, limit=5), start=1):
        if result.qualified_name in expected:
            return position
    return None


def read_results(tag: str) -> list[dict]:
    if not RESULTS_FILE.exists():
        return []
    rows = [json.loads(line) for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r["tag"] == tag]


def run(args) -> None:
    data = json.loads((EVAL_DIR / f"{args.file}.json").read_text(encoding="utf-8"))
    repo_id = get_repo_id(data["repo"])
    file_lengths = get_file_lengths(repo_id)

    done = {r["id"] for r in read_results(args.tag)}
    todo = [q for q in data["questions"] if q["id"] not in done][: args.limit]
    if not todo:
        print("Every question already has a result for this tag. Use --report, or a new --tag.")
        return

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    for item in todo:
        expected_chunks = get_expected_chunks(repo_id, item["expected"])
        known = {row[0] for row in expected_chunks}
        missing = [n for n in item["expected"] if n not in known]
        if missing:
            print(f"WARNING {item['id']}: expected names not in the index: {missing}")
        if not known:
            print(f"Skipping {item['id']}: none of its expected names exist.")
            continue

        print(f"\n{item['id']}: {item['q']}")
        start = time.time()
        try:
            result = ask(repo_id, item["q"])
        except Exception as error:  # most likely the free quota or rate limit
            print(f"Stopping: {error}")
            break
        seconds = round(time.time() - start, 1)

        scores = score_answer(result.answer, result.steps, expected_chunks, file_lengths)
        record = {
            "tag": args.tag,
            "id": item["id"],
            "question": item["q"],
            "answer": result.answer,
            "tools": [f"{s.name}({json.dumps(s.arguments)})" for s in result.steps],
            "calls": len(result.steps),
            "tokens": result.tokens,
            "seconds": seconds,
            "hit_step_limit": result.hit_step_limit,
            "search_rank": search_rank(repo_id, item["q"], known),
            "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **scores,
        }
        with RESULTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        print(
            f"  found={scores['found']}  citations: {scores['real']}/{scores['cited']} real, "
            f"{scores['seen']}/{scores['cited']} seen  |  {record['calls']} calls, "
            f"{record['tokens']} tokens, {seconds}s"
        )
        time.sleep(PAUSE_BETWEEN_QUESTIONS)


def report(tag: str) -> None:
    rows = read_results(tag)
    if not rows:
        print(f"No results yet for tag {tag!r}.")
        return

    print(f"{'id':<5}{'question':<46}{'search':>7}{'agent':>7}{'real':>7}{'seen':>7}{'calls':>6}{'tokens':>8}")
    for r in rows:
        search = f"#{r['search_rank']}" if r["search_rank"] else "miss"
        agent = "yes" if r["found"] else "no"
        print(
            f"{r['id']:<5}{r['question'][:44]:<46}{search:>7}{agent:>7}"
            f"{str(r['real']) + '/' + str(r['cited']):>7}{str(r['seen']) + '/' + str(r['cited']):>7}"
            f"{r['calls']:>6}{r['tokens']:>8}"
        )

    n = len(rows)
    cited = sum(r["cited"] for r in rows) or 1
    print(f"\nOver {n} questions (tag {tag!r}):")
    print(f"  plain search found an expected function in its top 5:  {sum(1 for r in rows if r['search_rank']) / n:.0%}")
    print(f"  agent answer cites an expected function:               {sum(1 for r in rows if r['found']) / n:.0%}")
    print(f"  citations that point to real lines:                    {sum(r['real'] for r in rows) / cited:.0%}")
    print(f"  citations the agent was actually shown by a tool:      {sum(r['seen'] for r in rows) / cited:.0%}")
    print(f"  average tool calls: {sum(r['calls'] for r in rows) / n:.1f}   "
          f"average tokens: {sum(r['tokens'] for r in rows) / n:,.0f}   "
          f"stopped at the step limit: {sum(1 for r in rows if r['hit_step_limit'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score the agent on a set of questions.")
    parser.add_argument("--file", default="agent_itsdangerous", help="eval file name, without .json")
    parser.add_argument("--tag", default="v1", help="label for this run; change it after you change the agent")
    parser.add_argument("--limit", type=int, default=3, help="how many unanswered questions to run now")
    parser.add_argument("--report", action="store_true", help="print results so far, run nothing")
    arguments = parser.parse_args()

    if arguments.report:
        report(arguments.tag)
    else:
        run(arguments)
        print()
        report(arguments.tag)