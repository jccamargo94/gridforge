---
name: documentation-maintainer
description: >
  Keeps gridforge documentation aligned with the real implementation (README, AGENTS,
  docs/ site, GitHub Pages workflow) — not an idealized roadmap. Use when documentation
  needs an update, a docs refresh, or a GitHub Pages publication pass; when a CLI, data
  pipeline, model, schema, deployment layout, or supported scenario changed and docs
  must follow. Trigger: /docs, "actualizar docs", "docs desactualizada", "refresh docs",
  "GitHub Pages", "documentación".
---

# Documentation maintainer

Use this skill when the repository needs documentation updates, a docs refresh, or a GitHub Pages publication pass.

## Goal

Ensure that the documentation reflects the real implementation of the project and that the public docs site is updated accordingly.

## Workflow

1. Review the current code paths that changed.
2. Update README and AGENTS with the new state and workflow.
3. Add or refresh a page under docs/ with concise, user-facing detail.
4. If the change impacts optimization logic, include the current mathematical formulation in the math page.
5. Verify that the GitHub Pages workflow still points to docs/.

## Checklist

- The landing page is still discoverable and navigable.
- The repo overview matches the live structure.
- Unsupported or partial capabilities are labeled clearly.
- The mathematical summary matches the current model structure.
