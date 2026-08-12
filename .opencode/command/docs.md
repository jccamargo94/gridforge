---
description: Ejecuta un pase completo de mantenimiento de documentación (README, AGENTS, docs/ y GitHub Pages) con el agente docs-maintainer.
agent: docs-maintainer
---

Ejecuta un pase completo de mantenimiento de documentación siguiendo tu skill
`documentation-maintainer` y las reglas de `.agents/rules/documentation.mdc` y
`.agents/rules/github-pages.mdc`:

1. Identifica los code paths que cambiaron recientemente (diff contra `develop`).
2. Actualiza README y AGENTS con el estado real.
3. Refresca o agrega páginas en `docs/`.
4. Si cambió la formulación matemática, actualiza la página de formulación y la landing.
5. Verifica que el workflow de GitHub Pages siga publicando `docs/`.

$ARGUMENTS
