"""Builds the bundled sample pull requests.

Each sample lives in samples/<id>/ as a `before/` tree, an `after/` tree and a `meta.json`
(repo, title, description, and the ground truth `expect`). The diff is produced by real
`git diff`, so hunk headers are exact. `expect.planted` lists the undisclosed changes a
reviewer should catch (ground truth for scripts/eval.py).

Run with: python scripts/build_samples.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
TARGET = ROOT / "src" / "pr_checker" / "data" / "samples.json"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd)}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True, encoding="utf8").stdout


def read_tree(root: Path) -> Dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_bytes().decode("utf8") for p in sorted(root.rglob("*")) if p.is_file()}


def write_tree(root: Path, tree: Dict[str, str]) -> None:
    for rel, content in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf8"))


def build(sample_dir: Path) -> dict:
    meta = json.loads((sample_dir / "meta.json").read_text(encoding="utf8"))
    before = read_tree(sample_dir / "before")
    after = read_tree(sample_dir / "after")
    work = Path(tempfile.mkdtemp(prefix="pr-checker-sample-"))
    try:
        git(work, "init", "-q")
        git(work, "config", "user.email", "sample@example.com")
        git(work, "config", "user.name", "sample")
        write_tree(work, before)
        git(work, "add", "-A")
        git(work, "commit", "-qm", "base")
        for rel in before:
            if rel not in after:
                (work / rel).unlink()
        write_tree(work, after)
        git(work, "add", "-A")
        diff = git(work, "diff", "--cached", "--no-color")
        return {k: meta[k] for k in ("id", "repo", "title", "hint", "description")} | {"diff": diff, "expect": meta["expect"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    order: List[str] = json.loads((SAMPLES / "order.json").read_text(encoding="utf8"))
    out = [build(SAMPLES / sample_id) for sample_id in order]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(f"Wrote {len(out)} samples to {TARGET}")


if __name__ == "__main__":
    main()
