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


def main(url: str) -> None:
    clean_url, owner, repo = parse_github_url(url)
    workdir = Path(tempfile.mkdtemp())
    dest = workdir / repo

    try:
        sha = clone_repo(clean_url, dest)
        print(f"Cloned {owner}/{repo} at commit {sha[:8]}")

        counts = Counter()
        for i, (path, language) in enumerate(iter_source_files(dest)):
            counts[language] += 1
            if i < 10:
                print(f"  {language:<11} {path.relative_to(dest)}")

        print(f"\nTotal source files: {sum(counts.values())}")
        print(dict(counts))
    finally:
        remove_repo(workdir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.list_files <github-url>")
    main(sys.argv[1])