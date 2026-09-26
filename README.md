# odoo-oca-addons

Platform-wide **published OCA catalog** for Agrista [Odoo.sh](https://www.odoo.sh)
umbrellas — corporator, capewools, agrifinance, and future apps. Each umbrella
pulls this repo as a **single** git submodule and installs a subset.

Synced from Agrista's `agrista/odoo-*` OCA forks on branch `19.0`. This is not
where you patch OCA code, and not where custom Agrista modules live.

## What this repo is

- The owned allowlist of OCA addons Agrista ships (`allowlist.yml`). Any
  umbrella may consume a subset; the catalog is not tied to one application's
  install list.
- Addon directories at the **repo root** (`queue_job/`, `brand/`, …) so Odoo.sh
  puts them on the addons path when the submodule is checked out.
- Sync tooling, a pin lockfile (`sources.lock.json`), and CI that refreshes the
  tree from fork SHAs.

## What this repo is not

- **Not** a place to edit addon code. Patch in `agrista/odoo-*` forks and send
  OCA `[19.0][MIG]` PRs from those forks; then re-run sync here.
- **Not** for custom Agrista modules (`agri_*`, `portfolio_*`,
  `certification_*`, `district`, `mapbox`, `catch_weight`, `traceability`,
  `mercator_sync`, …). Those stay in [`agrista/odoo-agrista`](https://github.com/agrista/odoo-agrista)
  (and related custom repos).
- **Not** a full OCA checkout. Sibling trees with no published entries in
  `allowlist.yml` are intentionally omitted.

## Layout

```text
allowlist.yml          # addon → source repo + path (data, not Python logic)
sources.lock.json      # pin SHAs + last sync result (including missing)
tools/sync.py          # copy allowlisted addon dirs from pinned forks
tools/sync_test.py
.github/workflows/sync.yml
queue_job/             # vendored allowlisted addons at repo root
brand/
…
```

Licenses stay as shipped in each addon folder (typically OCA LGPL-3). Do not
relicense.

## Add an addon to the allowlist

1. Confirm it belongs in the platform catalog: needed by ≥1 Agrista product or
   by shared infra. (Corporator's `installed_modules` / closure was the
   **historical seed**, not ongoing ownership.)
2. Ensure it exists on the Agrista fork's `19.0` branch (patch/migrate there
   first if needed). Sibling forks may not have `19.0` yet — sync records
   missing paths until forks open `19.0` / MIGs land; it will not invent files.
3. Add an entry to `allowlist.yml`:

   ```yaml
   my_addon:
     repo: agrista/odoo-some-project
     path: my_addon
   ```

4. Run sync (updates pins to current `19.0` tips):

   ```bash
   pip install -r requirements.txt
   python tools/sync.py --repo-root . --update-pins
   ```

5. Commit the allowlist, lockfile, and new addon tree. Or use the
   **Sync OCA allowlist** GitHub Action (`workflow_dispatch`).

If the source path is missing at the pin SHA, sync **skips** it and records it
under `missing` in `sources.lock.json` — it will not invent files.

## Sync locally

```bash
pip install -r requirements.txt
pytest -q                    # sync tool tests
python tools/sync.py --repo-root . --update-pins
# Re-run with the same pins → no-op for content (lockfile timestamp may change)
python tools/sync.py --repo-root .
```

Optional: `SYNC_GITHUB_TOKEN` for private sibling clones.

## GitHub Action / `SYNC_GITHUB_TOKEN`

Workflow: `.github/workflows/sync.yml` (`workflow_dispatch` + weekly schedule).

It checks out this repo, fetches pinned (or tip) `agrista/odoo-*` trees, runs
`tools/sync.py`, and opens a PR against `19.0` if the tree changed.

| Secret | Purpose |
|--------|---------|
| `SYNC_GITHUB_TOKEN` | Org/repo secret with **read** access to `agrista/odoo-*` source forks when those repos are **private**. Also usable to push the sync PR branch. |

**Important:** the default `GITHUB_TOKEN` for this workflow **cannot** read other
private repositories in the org. If siblings are private and
`SYNC_GITHUB_TOKEN` is unset or lacks access, the workflow **fails clearly**
rather than syncing an empty/partial tree. Public forks can be cloned without
it; still configure the secret before flipping forks to private.

Do not commit tokens. Do not invent a token in CI — configure the org secret in
GitHub Settings.

## Umbrellas: consume this submodule

Each Odoo.sh umbrella adds this repo once and installs only the modules it
needs (separate PR in that umbrella; not done from here):

1. Remove per-project OCA submodules now covered by this catalog. Keep custom
   submodules such as `src/agrista`.
2. Add a single submodule:

   ```gitconfig
   [submodule "src/oca"]
       path = src/oca
       url = git@github.com:agrista/odoo-oca-addons.git
       branch = 19.0
   ```

3. Point Odoo addons path / Odoo.sh config at `src/oca` (repo root of this
   bundle) instead of many `src/<oca-project>` paths.
4. On Odoo.sh, replace many deploy keys with **one** for
   `agrista/odoo-oca-addons`.

Suggested clone:

```bash
git submodule add -b 19.0 git@github.com:agrista/odoo-oca-addons.git src/oca
```

## Branching

- Default working branch for the Odoo 19 bundle: **`19.0`**.
- `main` may exist as the GitHub default; prefer opening sync PRs into `19.0`.
