import sys
import tempfile
from collections import Counter
from pathlib import Path

from app.ingest.clone import (
    clone_repo,
    iter_source_files,
    parse_github_url,
    remove_repo,
)
from app.parsing import parse_python


def main(url: str) -> None:
    clean_url, owner, repo = parse_github_url(url)
    workdir = Path(tempfile.mkdtemp())
    dest = workdir / repo

    try:
        sha = clone_repo(clean_url, dest)
        print(f"Cloned {owner}/{repo} at commit {sha[:8]}")

        kinds = Counter()
        files = 0
        shown = 0

        for path, language in iter_source_files(dest):
            if language != "python":
                continue

            rel = path.relative_to(dest).as_posix()
            parsed = parse_python(path.read_bytes(), rel)
            files += 1

            for s in parsed.symbols:
                kinds[s.kind] += 1
                if shown < 25:
                    print(f"{s.kind:<9} {rel}:{s.start_line}-{s.end_line}  {s.qualified_name}")
                    shown += 1

        print(f"\nParsed {files} Python files -> {dict(kinds)}")
    finally:
        remove_repo(workdir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.parse_repo <github-url>")
    main(sys.argv[1])