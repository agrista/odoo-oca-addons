# Sync tooling

`sync.py` copies allowlisted addon directories from pinned `agrista/odoo-*`
checkouts into the repository root.

```bash
pip install -r requirements.txt
pytest -q
python tools/sync.py --repo-root .. --update-pins   # if cwd is tools/
python tools/sync.py --repo-root . --update-pins    # from repo root
```

Allowlist data lives in `/allowlist.yml` (not hardcoded in Python). Pins and
last sync metadata live in `/sources.lock.json`.
