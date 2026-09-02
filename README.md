# odoo-oca-addons

Thin **allowlist** of OCA addons for [Odoo.sh](https://www.odoo.sh), pulled by
[`agrista/corporator`](https://github.com/agrista/corporator) as a **single**
git submodule.

Synced from Agrista's `agrista/odoo-*` OCA forks on branch `18.0`. This is not
where you patch OCA code, and not where custom Agrista modules live.

## What this repo is

- A materialized copy of only the OCA addons Gerber installs (see
  `allowlist.yml`).
- Addon directories at the **repo root** (`queue_job/`, `brand/`, …) so Odoo.sh
  puts them on the addons path when the submodule is checked out.
- Sync tooling, a pin lockfile (`sources.lock.json`), and CI that refreshes the
  tree from fork SHAs.

## What this repo is not

- **Not** a place to edit addon code. Patch in `agrista/odoo-*` forks and send
  OCA `[18.0][MIG]` PRs from those forks; then re-run sync here.
- **Not** for custom Agrista modules (`agri_*`, `portfolio_*`,
  `certification_*`, `district`, `mapbox`, `catch_weight`, `traceability`,
  `mercator_sync`, …). Those stay in [`agrista/odoo-agrista`](https://github.com/agrista/odoo-agrista)
  (and related custom repos).
- **Not** a full OCA checkout. Sibling trees like `odoo-server-tools`,
  `odoo-social`, `odoo-connector` are intentionally omitted when they have no
  Gerber-installed addons.

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

1. Confirm it is installed (or required by closure) in corporator
   `tools/installed_modules.txt` / `tools/closure.out.json`.
2. Ensure it exists on the Agrista fork's `18.0` branch (patch/migrate there
   first if needed).
3. Add an entry to `allowlist.yml`:

   ```yaml
   my_addon:
     repo: agrista/odoo-some-project
     path: my_addon
   ```

4. Run sync (updates pins to current `18.0` tips):

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
`tools/sync.py`, and opens a PR against `18.0` if the tree changed.

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

## Corporator: switch to this submodule (follow-up PR)

Do this in **agrista/corporator** (separate PR; not done from this repo):

1. Remove the per-project OCA submodules from `.gitmodules` / `src/*` that are
   now covered here (queue, web, brand, knowledge, management-system,
   multi-company, partner-contact, purchase-workflow, reporting-engine,
   server-ux, stock-logistics-workflow, website, account-financial-reporting,
   and unused ones like server-tools / social if you drop them in the same
   change). Keep `src/agrista` and other custom submodules.
2. Add a single submodule:

   ```gitconfig
   [submodule "src/oca"]
       path = src/oca
       url = git@github.com:agrista/odoo-oca-addons.git
       branch = 18.0
   ```

3. Point Odoo addons path / Odoo.sh config at `src/oca` (repo root of this
   bundle) instead of the many `src/<oca-project>` paths.
4. On Odoo.sh, replace the many deploy keys / submodule credentials with **one**
   deploy key (or deploy-key equivalent) for `agrista/odoo-oca-addons`.

Suggested clone:

```bash
git submodule add -b 18.0 git@github.com:agrista/odoo-oca-addons.git src/oca
```

## Branching

- Default working branch for the Odoo 18 bundle: **`18.0`**.
- `main` may exist as the GitHub default; prefer opening sync PRs into `18.0`.
