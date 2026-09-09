# Archive Report: time-series-db (series horarias)

**Change**: time-series-db — hourly `hourly_series` storage, tenant model, writers, serving, backfill
**Archived**: 2026-09-09 → `openspec/changes/archive/2026-09-09-time-series-db/`
**Branch**: `fase8a-time-series-db` off develop @ `38c4fe4e7` — HEAD `1c9e4f533` (7 apply commits + 2 docs commits)
**Delivery**: single PR vs develop (maintainer-approved `size:exception`, forecast 1400–1800 lines honored); PR NOT yet opened at close of archive
**Artifact store**: hybrid (Engram + OpenSpec)

## Terminal state (AT CLOSE — authoritative over intermediate snapshots)

- Verify verdict: **PASS**, 8/8 requirements, 16/16 spec scenarios compliant, `uv run pytest -q` → **467 passed** (exit 0, ruff clean), per `verify-report.md` committed at `1c9e4f533` (Engram #555). 0 blockers, 0 criticals, 0 warnings; 3 SUGGESTION-level findings (S1–S3 below).
- Exactly 3 new tables (`tenants`, `tenant_members`, `hourly_series`), Alembic `0007`/`0008` (linear chain `0001→…→0006→0007→0008`, `0008` = head — re-verified read-only at archive: no 0009 exists). No partitioning/RLS/Timescale/pg_partman (proposal Fuera). No frontend files touched.
- Tasks: 16/16 `[x]` (U1–U4), suite grew 440 → 467 across apply commits `6982aeb03`…`dfc05b54d`.
- B1 (product decision, Engram #550 `sdd/time-series-db/tenant-model`) is the binding attribution rule: private-run owner in >1 tenants → rows under EVERY member tenant (never public); 0 memberships → no rows. Design.md D4 prose amended at archive to match B1 (see D4 amendment below).

## Gates

- **Task Completion Gate**: PASS. Archived `tasks.md` has zero unchecked implementation boxes (`grep -c "\- \[ \]"` → 0). No stale-checkbox reconciliation was needed.
- **CRITICAL gate**: PASS. `verify-report` records `critical_findings: 0`, `blockers: 0`.
- **Native Review Receipt Gate**: `reviewGate` structurally absent from the launch status — no review was ever discovered for this candidate. Archive proceeds under ordinary repository policy; no receipt to validate, no `disabled/unmanaged` carve-out applicable.
- **Action Context Guard**: repo-local mode; every archive operation stayed inside `openspec/` (spec sync, design edit, folder move, report write). No production code, migrations, or tests touched.
- **`rules.archive`** (openspec/config.yaml: "Warn before merging destructive deltas"): no warning required — home-chart merge is additive (2 ADDED requirements + obsolete-narrative fix, no requirement removed) and hourly-series is a new domain (mechanical copy).

## Specs synced

| Domain | Action | Details |
|--------|--------|---------|
| home-chart | Updated | `openspec/specs/home-chart/spec.md` (+34/−2): **narrative fix** per the delta's supersede note — Proposito no longer says the backend is "dado y congelado" / "Solo frontend"; No objetivos drops "cambio backend" (backend changed in this change; frontend visual unchanged). **ADDED** REQ-HC-01 (daily mean derived from `hourly_series`, winner-run priority) + REQ-HC-02 (hourly values exposed, `*_hourly`, public + per-tenant) with scenarios SCN-HC-01-01/02, SCN-HC-02-01/02, appended verbatim from the delta. All 7 pre-existing frontend requirements preserved untouched. Spanish ASCII consistent with the file. |
| hourly-series | Created | `openspec/specs/hourly-series/spec.md` — full spec (no prior main spec existed), byte-identical mechanical copy of `specs/hourly-series/spec.md` (REQ-HS-01..06, SCN-HS-01-01..06-02), verified by empty `diff -r` readback. |

Synced requirements total: home-chart 7 pre-existing + 2 new = 9; hourly-series 6 new. No MODIFIED/REMOVED/RENAMED requirement blocks anywhere. Spec-vs-verify cross-check at close: 8/8 requirement IDs (REQ-HS-01..06 + REQ-HC-01/02) and 16/16 scenario IDs in the verify compliance matrix match the synced main specs exactly; no spec requirement contradicts the verify report.

## D4 amendment (verify SUGGESTION S2 — applied at archive, pre-move)

Design.md (archived copy) D4 prose amended from "owner in 0 or >1 tenants → write nothing" to "owner in >1 tenants → every member tenant (B1, product decision `sdd/time-series-db/tenant-model`); in 0 tenants → write nothing". The `## Open Questions` bullet was marked RESOLVED by B1 (multi-tenant attribution writes every member tenant; tenant *choice* per run remains the future option if ever needed). Behavior, tests (48-row multi-tenant test), and design docs are now aligned. The design edit happened BEFORE the snapshot, so the archived `design.md` is byte-identical to the amended file (empty `diff -r`).

## Post-archive notes (verify SUGGESTIONs S1 & S3 — do NOT block, operator follow-ups)

1. **S1 — constant-value goldens**: `test_api_chart.py`/`test_series_golden.py` seed constant hourly values, so `daily == mean(hours)` cannot discriminate a broken aggregation. Proven sound at verify time via a non-constant runtime probe (daily 111.5 == mean of 24 distinct values `100.0 + hour`). Future improvement: a permanent suite test with varying per-hour values.
2. **S3 — real backfill not run**: `data/` (~378M real CSVs) exists, but the one-time backfill (`python -m app.db.series`) was only exercised at fixture level (48 rows, idempotent, twice) and in the verify CLI probe. Operator note: run `python -m app.db.series` after deploying migrations `0007`/`0008`, per rollout order (upgrade → backfill → deploy code; design.md Rollout). Backfill replays done runs with CURRENT memberships — accepted, documented in apply-progress.

## Archive contents

- proposal.md ✅ (final closed-decision revision, FS)
- explore.md ✅
- specs/home-chart/spec.md ✅ (delta)
- specs/hourly-series/spec.md ✅ (full spec)
- design.md ✅ (D4/B1-amended — see above)
- tasks.md ✅ (16/16 checkboxes complete, zero unchecked)
- verify-report.md ✅ (PASS)
- archive-report.md ✅ (this file, additive — excluded from the move readback by design)

No `state.yaml` and no `apply-progress.md` file existed in this change folder (apply-progress lives in Engram only, #554) — nothing missing; contents moved are exactly the tracked change folder. Active `openspec/changes/` now contains only `archive/`.

## Lineage (Engram observation IDs actually read)

| Artifact | Topic key | Observation ID |
|----------|-----------|----------------|
| explore | sdd/time-series-db/explore | #548 |
| proposal | sdd/time-series-db/proposal | #549 |
| tenant-model decision (B1) | sdd/time-series-db/tenant-model | #550 |
| spec (hourly-series full spec + home-chart delta) | sdd/time-series-db/spec | #551 |
| design | sdd/time-series-db/design | #552 |
| tasks | sdd/time-series-db/tasks | #553 |
| apply-progress | sdd/time-series-db/apply-progress | #554 |
| verify-report | sdd/time-series-db/verify-report | #555 |

Archive report persisted as `sdd/time-series-db/archive-report` (project gridforge).

## Recorded discrepancies (per Final-State Authority — stated, not silently resolved)

1. **Engram proposal #549 is the pre-decision draft** (saved 16:11, Revisions: 1): it shows "Decisión abierta (producto)", `tenant_id` default = `user_id`, NO `tenants` table, and `hourly_series` alone via migration `0007`. The archived filesystem `proposal.md` is the later, closed-decision revision (16:13): `tenants` + `tenant_members` via `0007`, `hourly_series` via `0008`, "Decisión cerrada (producto)" referencing the tenant-model decision. Spec #551, design #552, verify #555, and the code (models/migrations 0007/0008) all corroborate the filesystem revision — it outranks the stale Engram obs under the ranking rules. The Engram proposal observation was never upserted post-decision.
2. **Engram spec #551 concatenates both delta specs** (hourly-series full spec + home-chart delta with its archive-supersede note) into one observation, mirroring the change folder at spec time. The synced main specs omit the supersede note by design (archive guidance, not spec content) — no contradiction.
3. **Engram design #552 predates the D4/B1 amendment** now present in the archived `design.md` (D4 prose + resolved open question). The amendment is documented in this report; behavior always matched B1 (tasks.md 2.5, apply status, verify Coherence table).

## Mechanical copy evidence

Step 2 (hourly-series full spec → `openspec/specs/hourly-series/spec.md`) and Step 3 (change folder → archive) were shell-only copies (`cp` to temp / `git mv`) with mandatory `diff -r` readbacks. Both readbacks were EMPTY (no differences) — verbatim outputs are in the phase result envelope. The home-chart merge and design D4 amendment are content merges (model-edited, diff-reviewed: home-chart spec `git diff` = +34/−2 exactly as intended; design.md `RM` in git status). The archive-report file is additive-only and was excluded from the source/destination comparison (it did not exist in the source snapshot).

## SDD Cycle Complete

The change was fully planned, implemented, verified, and archived. Source of truth (`openspec/specs/home-chart/spec.md`, `openspec/specs/hourly-series/spec.md`) reflects the shipped behavior. Remaining delivery steps (PR creation/merge, deployment of 0007/0008 + backfill) are orchestrator/operator actions.
