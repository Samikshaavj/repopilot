import sys

from app.search import hybrid_search, keyword_search, name_search, vector_search


def show(title, results, limit=5):
    print(f"=== {title} ===")
    if not results:
        print("(no results)\n")
        return
    for i, r in enumerate(results[:limit], start=1):
        print(f"{i}. [{r.score:.3f}] {r.kind} {r.qualified_name}")
        print(f"   {r.path}:{r.start_line}-{r.end_line}")
    print()


def main(repo_id: int, question: str, include_tests: bool) -> None:
    show("HYBRID (combined)", hybrid_search(repo_id, question, include_tests=include_tests))
    show("vector", vector_search(repo_id, question, include_tests=include_tests))
    show("keyword", keyword_search(repo_id, question, include_tests=include_tests))
    show("name", name_search(repo_id, question, include_tests=include_tests))


if __name__ == "__main__":
    args = sys.argv[1:]
    include_tests = "--tests" in args
    args = [a for a in args if a != "--tests"]
    if len(args) < 2:
        sys.exit("Usage: python -m scripts.search <repo_id> <question> [--tests]")
    main(int(args[0]), " ".join(args[1:]), include_tests)