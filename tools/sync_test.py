"""Tests for the OCA allowlist sync tool.

Uses small fake source trees — do not vendor real OCA addon trees in fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sync import (
    AllowlistError,
    load_allowlist,
    load_lockfile,
    save_lockfile,
    sync_addon,
    sync_from_checkouts,
)


def _write_addon(root: Path, name: str, body: str = "# addon\n") -> Path:
    addon = root / name
    addon.mkdir(parents=True, exist_ok=True)
    (addon / "__manifest__.py").write_text(
        "{'name': %r, 'installable': True}\n" % name, encoding="utf-8"
    )
    (addon / "__init__.py").write_text(body, encoding="utf-8")
    (addon / "LICENSE").write_text("LGPL-3\n", encoding="utf-8")
    return addon


def _write_allowlist(path: Path, addons: dict) -> None:
    path.write_text(
        yaml.safe_dump({"branch": "18.0", "addons": addons}, sort_keys=False),
        encoding="utf-8",
    )


def test_load_allowlist_maps_addon_to_repo_and_path(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {
            "queue_job": {
                "repo": "agrista/odoo-queue",
                "path": "queue_job",
            },
            "brand": {"repo": "agrista/odoo-brand", "path": "brand"},
        },
    )

    allowlist = load_allowlist(allowlist_path)

    assert allowlist.branch == "18.0"
    assert allowlist.addons["queue_job"].repo == "agrista/odoo-queue"
    assert allowlist.addons["queue_job"].path == "queue_job"
    assert set(allowlist.addons) == {"queue_job", "brand"}


def test_sync_copies_only_allowlisted_addon_directories(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    queue_src = sources / "odoo-queue"
    _write_addon(queue_src, "queue_job", body="# allowlisted\n")
    _write_addon(queue_src, "queue_job_batch", body="# not allowlisted\n")

    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {
            "queue_job": {
                "repo": "agrista/odoo-queue",
                "path": "queue_job",
            },
        },
    )
    allowlist = load_allowlist(allowlist_path)
    checkouts = {"agrista/odoo-queue": queue_src}
    pins = {"agrista/odoo-queue": "abc123"}

    result = sync_from_checkouts(allowlist, checkouts, dest, pins)

    assert (dest / "queue_job" / "__manifest__.py").is_file()
    assert (dest / "queue_job" / "LICENSE").read_text(encoding="utf-8") == "LGPL-3\n"
    assert not (dest / "queue_job_batch").exists()
    assert "queue_job" in result.synced
    assert result.synced["queue_job"]["sha"] == "abc123"
    assert result.missing == []


def test_sync_refuses_non_allowlisted_addon(tmp_path: Path) -> None:
    sources = tmp_path / "sources" / "odoo-queue"
    _write_addon(sources, "queue_job_batch")
    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {"queue_job": {"repo": "agrista/odoo-queue", "path": "queue_job"}},
    )
    allowlist = load_allowlist(allowlist_path)

    with pytest.raises(AllowlistError, match="not allowlisted"):
        sync_addon(
            allowlist,
            addon="queue_job_batch",
            source_root=sources,
            dest_root=dest,
            repo="agrista/odoo-queue",
            sha="deadbeef",
        )

    assert not (dest / "queue_job_batch").exists()


def test_lockfile_records_source_repo_and_sha(tmp_path: Path) -> None:
    lock_path = tmp_path / "sources.lock.json"
    sources = tmp_path / "sources" / "odoo-brand"
    _write_addon(sources, "brand")
    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {"brand": {"repo": "agrista/odoo-brand", "path": "brand"}},
    )
    allowlist = load_allowlist(allowlist_path)

    result = sync_from_checkouts(
        allowlist,
        {"agrista/odoo-brand": sources},
        dest,
        {"agrista/odoo-brand": "pinsha1"},
    )
    save_lockfile(lock_path, result.lockfile)
    loaded = load_lockfile(lock_path)

    assert loaded["branch"] == "18.0"
    assert loaded["sources"]["agrista/odoo-brand"]["sha"] == "pinsha1"
    assert loaded["synced"]["brand"]["repo"] == "agrista/odoo-brand"
    assert loaded["synced"]["brand"]["sha"] == "pinsha1"
    assert loaded["synced"]["brand"]["path"] == "brand"


def test_overwrite_on_sync_replaces_destination_tree(tmp_path: Path) -> None:
    sources = tmp_path / "sources" / "odoo-web"
    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {"web_refresher": {"repo": "agrista/odoo-web", "path": "web_refresher"}},
    )
    allowlist = load_allowlist(allowlist_path)

    _write_addon(sources, "web_refresher", body="# v1\n")
    sync_from_checkouts(
        allowlist,
        {"agrista/odoo-web": sources},
        dest,
        {"agrista/odoo-web": "sha1"},
    )
    assert (dest / "web_refresher" / "__init__.py").read_text(encoding="utf-8") == "# v1\n"
    # Stale file that must disappear on overwrite
    (dest / "web_refresher" / "stale.txt").write_text("gone\n", encoding="utf-8")

    (sources / "web_refresher" / "__init__.py").write_text("# v2\n", encoding="utf-8")
    sync_from_checkouts(
        allowlist,
        {"agrista/odoo-web": sources},
        dest,
        {"agrista/odoo-web": "sha2"},
    )

    assert (dest / "web_refresher" / "__init__.py").read_text(encoding="utf-8") == "# v2\n"
    assert not (dest / "web_refresher" / "stale.txt").exists()


def test_missing_source_addon_is_recorded_and_skipped(tmp_path: Path) -> None:
    sources = tmp_path / "sources" / "odoo-knowledge"
    sources.mkdir(parents=True)
    _write_addon(sources, "document_page")
    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {
            "document_page": {
                "repo": "agrista/odoo-knowledge",
                "path": "document_page",
            },
            "document_page_procedure": {
                "repo": "agrista/odoo-knowledge",
                "path": "document_page_procedure",
            },
        },
    )
    allowlist = load_allowlist(allowlist_path)

    result = sync_from_checkouts(
        allowlist,
        {"agrista/odoo-knowledge": sources},
        dest,
        {"agrista/odoo-knowledge": "sha-k"},
    )

    assert (dest / "document_page").is_dir()
    assert not (dest / "document_page_procedure").exists()
    assert len(result.missing) == 1
    assert result.missing[0]["addon"] == "document_page_procedure"
    assert "document_page_procedure" not in result.synced


def test_resync_same_pins_is_noop_for_lockfile_content(tmp_path: Path) -> None:
    sources = tmp_path / "sources" / "odoo-queue"
    _write_addon(sources, "queue_job")
    dest = tmp_path / "dest"
    dest.mkdir()
    allowlist_path = tmp_path / "allowlist.yml"
    _write_allowlist(
        allowlist_path,
        {"queue_job": {"repo": "agrista/odoo-queue", "path": "queue_job"}},
    )
    allowlist = load_allowlist(allowlist_path)
    pins = {"agrista/odoo-queue": "same-sha"}

    first = sync_from_checkouts(allowlist, {"agrista/odoo-queue": sources}, dest, pins)
    second = sync_from_checkouts(allowlist, {"agrista/odoo-queue": sources}, dest, pins)

    assert json.dumps(first.lockfile["synced"], sort_keys=True) == json.dumps(
        second.lockfile["synced"], sort_keys=True
    )
    assert first.lockfile["sources"] == second.lockfile["sources"]
