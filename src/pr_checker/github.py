from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Optional

import httpx

from .config import config
from .jsutil import js_strip
from .models import PullRequestInput
from .units import LIMITS

_PR_URL = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)", re.I)


class GitHubError(Exception):
    pass


def parse_pr_url(url: str) -> Optional[Dict[str, object]]:
    m = _PR_URL.match(js_strip(url))
    return {"owner": m.group(1), "repo": m.group(2), "number": int(m.group(3))} if m else None


async def fetch_pull_request(url: str) -> PullRequestInput:
    """Fetches a public pull request's title, description and diff from the GitHub REST API."""
    ref = parse_pr_url(url)
    if not ref:
        raise GitHubError("Expected a URL like https://github.com/owner/repo/pull/123")
    api = f"https://api.github.com/repos/{ref['owner']}/{ref['repo']}/pulls/{ref['number']}"
    headers = {"User-Agent": "pr-checker", "X-GitHub-Api-Version": "2022-11-28"}
    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"

    async def get(client: httpx.AsyncClient, accept: str) -> httpx.Response:
        try:
            res = await client.get(api, headers={**headers, "Accept": accept})
        except httpx.HTTPError as err:
            raise GitHubError(f"Could not reach GitHub: {err}") from err
        if res.status_code == 404:
            raise GitHubError("Pull request not found (private repositories need GITHUB_TOKEN).")
        if res.status_code in (403, 429):
            reset = res.headers.get("x-ratelimit-reset")
            when = ""
            if reset:
                try:
                    when = f" Try again after {datetime.fromtimestamp(int(reset)).strftime('%-I:%M:%S %p')}."
                except (ValueError, OSError):
                    pass
            raise GitHubError(f"GitHub rate limit reached.{when} Set GITHUB_TOKEN to raise it, or paste the diff instead.")
        if res.status_code >= 400:
            raise GitHubError(f"GitHub returned {res.status_code}.")
        return res

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        meta = (await get(client, "application/vnd.github+json")).json()
        diff = (await get(client, "application/vnd.github.diff")).text
    size = len(diff.encode("utf8"))
    if size > LIMITS["max_diff_bytes"]:
        raise GitHubError(f"This PR's diff is {round(size / 1000)} KB, over the {LIMITS['max_diff_bytes'] // 1000} KB limit.")

    return PullRequestInput(
        title=meta["title"],
        description=js_strip(re.sub(r"<!--[\s\S]*?-->", "", meta.get("body") or "")),
        diff=diff,
        source=f"{ref['owner']}/{ref['repo']}#{ref['number']}",
    )
