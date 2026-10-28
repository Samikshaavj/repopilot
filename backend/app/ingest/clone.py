import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Iterator

# Folders we never want to look inside
IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages", ".idea", ".vscode",
}

# Skip files bigger than this (usually generated or minified code)
MAX_FILE_BYTES = 500_000

# Which file extensions we understand, and what language they are
LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

# Matches only: https://github.com/<owner>/<repo>
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str, str]:
    """Validate a GitHub URL. Returns (clean_url, owner, repo)."""
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError(
            "Enter a public GitHub repository URL like https://github.com/owner/repo"
        )
    owner, repo = match.groups()
    if repo in (".", ".."):
        raise ValueError("Invalid repository name")
    return f"https://github.com/{owner}/{repo}", owner, repo


def clone_repo(url: str, dest: Path) -> str:
    """Shallow-clone `url` into `dest`. Returns the commit SHA that was cloned."""
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")

    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", "--", url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    result = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def iter_source_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (file_path, language) for every source file under `root`."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Edit the list in place so os.walk never enters ignored folders
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)

        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            language = LANGUAGE_BY_EXT.get(path.suffix)
            if language is None:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            yield path, language


def _make_writable_and_retry(func, path, exc):
    # Windows marks some git files read-only, which blocks deletion
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_repo(path: Path) -> None:
    """Delete a cloned repo folder (works around Windows read-only git files)."""
    shutil.rmtree(path, onexc=_make_writable_and_retry)