import sys

from app.indexer import index_repository

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.index_repo <github-url>")
    index_repository(sys.argv[1])