import sys

from app.tools import run_tool

DEMOS = [
    ("search_code", {"query": "how does token expiry work"}),
    ("search_code", {"query": "BadSignature", "limit": 2}),
    ("read_file", {"path": "src/itsdangerous/exc.py", "start_line": 20, "end_line": 35}),
    ("read_file", {"path": "does/not/exist.py"}),
    ("get_callees", {"symbol": "Serializer.loads", "depth": 2}),
    ("get_callers", {"symbol": "Signer.derive_key"}),
    ("list_files", {"prefix": "src/"}),
    ("no_such_tool", {}),
]

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.try_tools <repo_id>")
    repo_id = int(sys.argv[1])
    for name, args in DEMOS:
        print("=" * 70)
        print(f"{name}({args})")
        print(run_tool(repo_id, name, args))
        print()