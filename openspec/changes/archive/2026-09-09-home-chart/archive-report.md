# Archive Report: home-chart (issue #90)

**Change**: home-chart — Home chart-first frontend (issue #90)
**Archived**: 2026-09-09 → `openspec/changes/archive/2026-09-09-home-chart/`
**Branch**: `fase7b-home-chart` off develop @ `03b63fbc3`
**Delivery**: PR #92 vs develop ("feat: chart-first Home with daily market price series"); issue #90 commented + closed
**Artifact store**: hybrid (Engram + OpenSpec)

## Terminal state (AT CLOSE — authoritative over intermediate snapshots)

- Verify verdict: **PASS WITH WARNINGS**, 7/7 requirements, 12/12 spec scenarios compliant, 31 new tests green (7 unit + 24 integration across 7 test files; focused run 56/56).
- The two non-zero gates are proven pre-existing on clean develop, excluded per session preflight: nodal hour-selector flake (`app/(app)/runs/[id]/nodal/page.test.tsx`, timeout only under full-parallel load, passes isolated on branch and develop) and nodal tsc error (`components/nodal/network-graph.test.tsx(214,12)`, zero diff vs develop, zero errors in changed files).
- Minor doc drift flagged by verify (apply-progress said "5 sibling fixtures", actual 6) was FIXED in docs commit `574d4929b` on the branch.
- Planning docs (proposal/spec/design/exploration/config.yaml) committed in `574d4929b`; change folder complete in-PR.
- Backend untouched: `git diff origin/develop...HEAD -- services/ app/ tests/` empty; only `frontend/` + `openspec/` differ.
- Explicitly NOT in PR (left uncommitted in worktree, pre-existing, orchestrator-owned): `.atl/skill-registry.md` + cache modifications, `handoff-issue-90-home-chart.md`.

## Gates

- **Task Completion Gate**: PASS. Archived `tasks.md` has zero unchecked boxes (`grep "- [ ]"` empty). No stale-checkbox reconciliation was needed.
- **CRITICAL gate**: PASS. `verify-report` records `critical_findings: 0`, `blockers: 0`.
- **Native Review Receipt Gate**: `reviewGate` structurally absent — no review was ever discovered for this candidate. Archive proceeds under ordinary repository policy; no receipt to validate.
- **Action Context Guard**: repo-local mode; all archive operations stayed inside the repo root.
- **`rules.archive`** (openspec/config.yaml: "Warn before merging destructive deltas"): no warning required — merge is purely additive (new domain, no existing spec touched).

## Specs synced

| Domain | Action | Details |
|--------|--------|---------|
| home-chart | Created | `openspec/specs/home-chart/spec.md` — 7 requirements, 12 scenarios, mechanical copy of delta (no prior main spec existed) |

No MODIFIED/REMOVED/RENAMED requirements; no existing specs were altered.

## Archive contents

- proposal.md ✅
- specs/home-chart/spec.md ✅
- design.md ✅
- exploration.md ✅
- tasks.md ✅ (10/10 checkboxes complete — see count note below)
- apply-progress.md ✅
- verify-report.md ✅ (PASS WITH WARNINGS)
- archive-report.md ✅ (this file, additive)

## Lineage (Engram observation IDs actually read)

| Artifact | Topic key | Observation ID |
|----------|-----------|----------------|
| proposal | sdd/home-chart/proposal | #534 |
| spec | sdd/home-chart/spec | #535 |
| design | sdd/home-chart/design | #536 |
| tasks | sdd/home-chart/tasks | #537 |
| apply-progress | sdd/home-chart/apply-progress | #538 |
| verify-report | sdd/home-chart/verify-report | #539 |

Archive report persisted as `sdd/home-chart/archive-report` (project gridforge).

## Recorded discrepancies (per Final-State Authority — stated, not silently resolved)

1. **Task count 10 vs 11**: `tasks.md` in the archive contains exactly 10 implementation checkbox lines (1.1–4.1), all `[x]`; `apply-progress.md` §Task status lists the same 10 items, all `[x]`. `verify-report` §Completeness, `apply-progress` §Status, and the Engram tasks observation (#537) label the set "11/11". Repository evidence (checkbox lines) shows 10; no artifact names an 11th task. Completion is unaffected under either count — zero unchecked work remains — but a future reader auditing the "11" figure should know the enumerated items are 10.
2. **Test totals by scope** (not a contradiction): 31 = new tests written by this change; 56 = focused run over all 7 test files the change creates or touches (includes pre-existing tests in touched files); 265/266 = full suite (sole failure is the pre-existing nodal flake above).
3. Snapshot-derived claims in `apply-progress` (#538, e.g. "PR NOT opened, branch NOT pushed") and task-gate prose in `tasks.md` §Gate status describe apply-phase time. Final delivery facts (PR #92 opened, branch pushed, issue #90 closed) come from the orchestrator launch prompt and outrank those snapshots.

## Mechanical copy evidence

Step 2 (delta → `openspec/specs/home-chart/spec.md`) and Step 3 (change folder → archive) were shell-only copies (`cp`/`git mv`) with mandatory `diff -r` readbacks. Both readbacks were empty (no differences). Verbatim outputs are in the phase result envelope.

## SDD Cycle Complete

The change was fully planned, implemented, verified, and archived. Source of truth (`openspec/specs/home-chart/spec.md`) reflects the shipped behavior. Ready for the next change.
