from __future__ import annotations

import re

LOCKFILES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
    "mix.lock",
    "pubspec.lock",
}

MANIFESTS = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "mix.exs",
    "pubspec.yaml",
}

BUILD_NAMES = {"Makefile", "Dockerfile", "CMakeLists.txt", "configure", "Justfile", "Rakefile", "Taskfile.yml"}

_CI = re.compile(r"^\.github/workflows/|^\.gitlab-ci\.ya?ml$|^\.circleci/|^jenkinsfile$|^azure-pipelines|^\.travis\.ya?ml$|^\.buildkite/")
_BUILD_EXT = re.compile(r"\.(sh|bash|zsh|ps1|mk)$")
_BUILD_DIR = re.compile(r"^(scripts|bin|\.husky)/")
_TEST = re.compile(r"(^|/)(__tests__|tests?|spec|e2e)/|\.(test|spec)\.[a-z]+$|_test\.(go|py)$|^test_.*\.py$")
_DOCS_EXT = re.compile(r"\.(md|mdx|rst|txt|adoc)$")
_DOCS_DIR = re.compile(r"^docs?/")
_DOCS_NAME = re.compile(r"^(license|changelog|authors|contributors)")
_ASSET = re.compile(r"\.(png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|otf|mp4|mp3|wav|pdf)$")
_CONFIG_EXT = re.compile(r"\.(json|ya?ml|toml|ini|cfg|conf|env|properties)$")
_RC = re.compile(r"(^|/)\.[a-z]+rc$")


def classify_path(path: str) -> str:
    name = path.split("/")[-1] or path
    lower = path.lower()

    if name in LOCKFILES:
        return "lockfile"
    if name in MANIFESTS:
        return "manifest"
    if _CI.search(lower):
        return "ci"
    if name in BUILD_NAMES or _BUILD_EXT.search(lower) or _BUILD_DIR.search(lower):
        return "build"
    if _TEST.search(lower):
        return "test"
    if _DOCS_EXT.search(lower) or _DOCS_DIR.search(lower) or _DOCS_NAME.search(name.lower()):
        return "docs"
    if _ASSET.search(lower):
        return "asset"
    if _CONFIG_EXT.search(lower) or _RC.search(lower):
        return "config"
    return "source"


_SENSITIVE = re.compile(
    r"(auth|login|logout|session|token|jwt|oauth|password|passwd|secret|credential|crypto|cipher|permission|acl|rbac|role|admin|security|sanitiz|csrf|cors|middleware|firewall|payment|billing|install|\.github/workflows)",
    re.I,
)


def is_sensitive_path(path: str) -> bool:
    """Paths where an unexplained change deserves a closer look regardless of content."""
    return bool(_SENSITIVE.search(path))
