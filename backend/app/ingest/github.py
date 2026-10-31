import json
import urllib.error
import urllib.request


def repo_size_kb(owner: str, repo: str) -> int | None:
    """Size of a public GitHub repository in KB, or None if GitHub could not be asked."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "repopilot"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(json.load(response)["size"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError("That repository was not found, or it is private.")
        return None  # for example: GitHub's anonymous rate limit. Do not block indexing for it.
    except Exception:
        return None