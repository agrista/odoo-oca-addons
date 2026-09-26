"""Materialize allowlisted OCA addons from agrista/odoo-* fork pins.

This repo is a thin allowlist bundle for Odoo.sh. Patch addon code in the
source forks; never edit vendored trees here except by re-running sync.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required. Install with: pip install pyyaml"
    ) from exc


REPO_ROOT_MARKERS = (
    "allowlist.yml",
    "sources.lock.json",
    "README.md",
    "tools",
    ".github",
    ".git",
    ".gitignore",
    "pyproject.toml",
    "requirements.txt",
    "LICENSE",
)


class AllowlistError(ValueError):
    """Raised when sync is asked to touch a non-allowlisted addon."""


@dataclass(frozen=True)
class AddonSource:
    repo: str
    path: str


@dataclass(frozen=True)
class Allowlist:
    branch: str
    addons: dict[str, AddonSource]


@dataclass
class SyncResult:
    synced: dict[str, dict[str, str]] = field(default_factory=dict)
    missing: list[dict[str, str]] = field(default_factory=list)
    lockfile: dict[str, Any] = field(default_factory=dict)


def load_allowlist(path: Path) -> Allowlist:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "addons" not in data:
        raise AllowlistError(f"invalid allowlist at {path}")
    addons: dict[str, AddonSource] = {}
    for name, entry in (data.get("addons") or {}).items():
        if not isinstance(entry, dict) or "repo" not in entry or "path" not in entry:
            raise AllowlistError(f"invalid allowlist entry for {name!r}")
        addons[name] = AddonSource(repo=str(entry["repo"]), path=str(entry["path"]))
    return Allowlist(branch=str(data.get("branch") or "19.0"), addons=addons)


def load_lockfile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "branch": "19.0",
            "generated_at": None,
            "sources": {},
            "synced": {},
            "missing": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_lockfile(path: Path, lockfile: dict[str, Any]) -> None:
    path.write_text(json.dumps(lockfile, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_addon_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def sync_addon(
    allowlist: Allowlist,
    *,
    addon: str,
    source_root: Path,
    dest_root: Path,
    repo: str,
    sha: str,
) -> dict[str, str]:
    """Copy one allowlisted addon from a source checkout into dest_root."""
    if addon not in allowlist.addons:
        raise AllowlistError(f"addon {addon!r} is not allowlisted")
    entry = allowlist.addons[addon]
    if entry.repo != repo:
        raise AllowlistError(
            f"addon {addon!r} is allowlisted from {entry.repo}, not {repo}"
        )
    src = source_root / entry.path
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    if not (src / "__manifest__.py").is_file():
        raise AllowlistError(f"source path {src} has no __manifest__.py")
    dest = dest_root / addon
    _copy_addon_tree(src, dest)
    return {"repo": repo, "sha": sha, "path": entry.path}


def sync_from_checkouts(
    allowlist: Allowlist,
    checkouts: dict[str, Path],
    dest_root: Path,
    pins: dict[str, str],
) -> SyncResult:
    """Sync all allowlisted addons from local checkouts pinned by SHA."""
    synced: dict[str, dict[str, str]] = {}
    missing: list[dict[str, str]] = []
    sources_meta: dict[str, dict[str, Any]] = {}

    for addon_name, entry in sorted(allowlist.addons.items()):
        sha = pins.get(entry.repo)
        if not sha:
            missing.append(
                {
                    "addon": addon_name,
                    "repo": entry.repo,
                    "path": entry.path,
                    "reason": "no pin SHA for source repo",
                }
            )
            continue
        checkout = checkouts.get(entry.repo)
        if checkout is None:
            missing.append(
                {
                    "addon": addon_name,
                    "repo": entry.repo,
                    "path": entry.path,
                    "reason": "source checkout not provided",
                }
            )
            continue
        src = checkout / entry.path
        if not src.is_dir() or not (src / "__manifest__.py").is_file():
            missing.append(
                {
                    "addon": addon_name,
                    "repo": entry.repo,
                    "path": entry.path,
                    "reason": "not found at pin",
                }
            )
            continue
        synced[addon_name] = sync_addon(
            allowlist,
            addon=addon_name,
            source_root=checkout,
            dest_root=dest_root,
            repo=entry.repo,
            sha=sha,
        )
        sources_meta.setdefault(
            entry.repo,
            {"sha": sha, "addons": []},
        )
        sources_meta[entry.repo]["addons"].append(addon_name)

    for meta in sources_meta.values():
        meta["addons"] = sorted(meta["addons"])

    lockfile = {
        "branch": allowlist.branch,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": dict(sorted(sources_meta.items())),
        "synced": dict(sorted(synced.items())),
        "missing": missing,
    }
    return SyncResult(synced=synced, missing=missing, lockfile=lockfile)


def lockfile_content_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Compare lockfile payload ignoring generated_at timestamp."""
    keys = ("branch", "sources", "synced", "missing")
    return all(a.get(k) == b.get(k) for k in keys)


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def resolve_branch_sha(
    repo: str,
    branch: str,
    *,
    cache_dir: Path,
    token: str | None = None,
) -> str:
    """Resolve the tip SHA of branch for repo (owner/name)."""
    url = _repo_url(repo, token)
    cache_dir.mkdir(parents=True, exist_ok=True)
    bare = cache_dir / f"{repo.replace('/', '__')}.git"
    if bare.is_dir():
        _run(["git", "fetch", "--depth", "1", "origin", branch], cwd=bare)
    else:
        _run(
            [
                "git",
                "clone",
                "--bare",
                "--depth",
                "1",
                "--branch",
                branch,
                url,
                str(bare),
            ]
        )
    return _run(["git", "rev-parse", f"refs/heads/{branch}"], cwd=bare)


def materialize_checkout(
    repo: str,
    sha: str,
    *,
    cache_dir: Path,
    work_dir: Path,
    token: str | None = None,
) -> Path:
    """Ensure work_dir contains a checkout of repo at sha; return work_dir."""
    url = _repo_url(repo, token)
    if work_dir.is_dir() and (work_dir / ".git").exists():
        _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=work_dir)
        _run(["git", "checkout", "--force", sha], cwd=work_dir)
        _run(["git", "clean", "-fdx"], cwd=work_dir)
        return work_dir
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.parent.mkdir(parents=True, exist_ok=True)
    # Prefer fetching the exact SHA when possible.
    _run(["git", "clone", "--no-checkout", url, str(work_dir)])
    try:
        _run(["git", "fetch", "--depth", "1", "origin", sha], cwd=work_dir)
    except subprocess.CalledProcessError:
        # Shallow clone tip may not contain an older pin; deepen.
        _run(["git", "fetch", "origin", sha], cwd=work_dir)
    _run(["git", "checkout", "--force", sha], cwd=work_dir)
    return work_dir


def _repo_url(repo: str, token: str | None) -> str:
    if token:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    return f"https://github.com/{repo}.git"


def managed_addon_dirs(dest_root: Path, allowlist: Allowlist) -> set[str]:
    """Return addon directory names currently present that are allowlisted."""
    present = set()
    for name in allowlist.addons:
        if (dest_root / name).is_dir():
            present.add(name)
    return present


def remove_stale_synced_addons(
    dest_root: Path,
    allowlist: Allowlist,
    previous_synced: dict[str, Any],
) -> list[str]:
    """Remove addon dirs that were previously synced but are no longer allowlisted."""
    removed: list[str] = []
    for name in sorted(previous_synced):
        if name in allowlist.addons:
            continue
        path = dest_root / name
        if path.is_dir() and path.name not in REPO_ROOT_MARKERS:
            shutil.rmtree(path)
            removed.append(name)
    return removed


def run_sync(
    repo_root: Path,
    *,
    update_pins: bool = False,
    token: str | None = None,
    cache_dir: Path | None = None,
) -> SyncResult:
    allowlist = load_allowlist(repo_root / "allowlist.yml")
    lock_path = repo_root / "sources.lock.json"
    previous = load_lockfile(lock_path)
    cache = cache_dir or (repo_root / ".cache" / "sources")

    repos = sorted({entry.repo for entry in allowlist.addons.values()})
    pins: dict[str, str] = {}
    for repo in repos:
        if update_pins:
            pins[repo] = resolve_branch_sha(
                repo, allowlist.branch, cache_dir=cache / "bare", token=token
            )
        elif repo in (previous.get("sources") or {}):
            pins[repo] = previous["sources"][repo]["sha"]
        else:
            pins[repo] = resolve_branch_sha(
                repo, allowlist.branch, cache_dir=cache / "bare", token=token
            )

    checkouts: dict[str, Path] = {}
    for repo, sha in pins.items():
        work = cache / "work" / repo.replace("/", "__")
        checkouts[repo] = materialize_checkout(
            repo, sha, cache_dir=cache, work_dir=work, token=token
        )

    remove_stale_synced_addons(repo_root, allowlist, previous.get("synced") or {})
    result = sync_from_checkouts(allowlist, checkouts, repo_root, pins)
    if lockfile_content_equal(previous, result.lockfile):
        # Preserve prior generated_at so same-pin re-runs leave git clean.
        result.lockfile["generated_at"] = previous.get("generated_at")
        if previous == result.lockfile:
            return result
    save_lockfile(lock_path, result.lockfile)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Path to oca-addons repo root",
    )
    parser.add_argument(
        "--update-pins",
        action="store_true",
        help="Re-resolve source SHAs from allowlist branch tips",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Git cache directory (default: <repo-root>/.cache/sources)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("SYNC_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        help="GitHub token for private sibling repos (env SYNC_GITHUB_TOKEN)",
    )
    args = parser.parse_args(argv)

    result = run_sync(
        args.repo_root.resolve(),
        update_pins=args.update_pins,
        token=args.token,
        cache_dir=args.cache_dir,
    )
    print(
        json.dumps(
            {
                "synced": sorted(result.synced),
                "missing": result.missing,
                "sources": {
                    repo: meta["sha"]
                    for repo, meta in result.lockfile.get("sources", {}).items()
                },
            },
            indent=2,
        )
    )
    if result.missing:
        print(
            f"WARNING: {len(result.missing)} allowlisted addon(s) missing at pin",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
