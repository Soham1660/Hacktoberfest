from __future__ import annotations

from .models import Change


def change_status(c: Change) -> str:
    """Where a change stands against the PR's claims."""
    if c.self_check is not None and c.self_check.outcome == "withdrawn":
        return "retracted"
    if c.contradicts:
        return "contradicts"
    if c.claims:
        return "explained"
    if c.effect in ("none", "cosmetic"):
        return "incidental"
    return "unexplained"
