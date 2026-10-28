import sys

from app.indexer import index_repository

if __name__ == "__main__":
    force = "--force" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if a != "--force"]
    if len(args) != 1:
        sys.exit("Usage: python -m scripts.index_repo <github-url> [--force]")
    index_repository(args[0], force=force)