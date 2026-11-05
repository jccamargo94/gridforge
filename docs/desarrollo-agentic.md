---
title: "Desarrollo agentic"
layout: default
---

# Cómo se construyó este proyecto

GridForge se desarrolla con asistentes de código bajo un proceso explícito y
auditable, no con prompts sueltos. Esta página describe ese proceso y señala los
artefactos reales del repositorio que lo respaldan. Es documentación técnica,
no un pitch.

## 1. Ciclo spec → plan → implementación

Cada fase o feature no trivial pasa por tres pasos, y cada paso deja un archivo
versionado:

1. **Spec** (`docs/superpowers/specs/`): problema, decisiones de diseño y
   alcance. Se escribe antes de tocar código.
2. **Plan** (`docs/superpowers/plans/`): tareas pequeñas y verificables, con los
   archivos a tocar y los tests que deben quedar verdes.
3. **Implementación** en una rama `fase<N><letra>-<nombre>`, ejecutada tarea por
   tarea con revisión entre tareas, y PR contra `develop` (nunca commits
   directos a `develop`).

### Caso de ejemplo: ingesta XM, mecanismo 2 (AGC por unidad)

| Paso | Artefacto |
|---|---|
| Plan | [`2026-08-11-ingesta-xm-mecanismo2-agc.md`](https://github.com/jccamargo94/gridforge/blob/develop/docs/superpowers/plans/2026-08-11-ingesta-xm-mecanismo2-agc.md) |
| Spec de la fundación | [`2026-08-06-ingesta-storage-xm-design.md`](https://github.com/jccamargo94/gridforge/blob/develop/docs/superpowers/specs/2026-08-06-ingesta-storage-xm-design.md) |
| PR resultante | [#33 `fase6b-ingesta-xm-mecanismo2`](https://github.com/jccamargo94/gridforge/pull/33) |

Otros pares spec + plan completos: Fase 3 (API y persistencia), LMP nodal
(motor, API/worker y frontend), scraper de topología PARATEC y ejecuciones
diarias. La lista completa está en
[`docs/superpowers/specs/`](https://github.com/jccamargo94/gridforge/tree/develop/docs/superpowers/specs).

## 2. Reglas persistentes para los agentes

El contexto que un agente debe conocer siempre vive en
[`.agents/rules/`](https://github.com/jccamargo94/gridforge/tree/develop/.agents/rules)
(formato `.mdc`, independiente del agente o IDE) y `AGENTS.md` actúa como índice:

- `overview.mdc`: dominio, layout, toolchain, flujo de trabajo y *gotchas*
  verificados (por ejemplo, las unidades de cada CSV de XM).
- `python-patterns.mdc`: convenciones reales de Pydantic v2, `Storage`, Pyomo y
  solver por defecto, y testing.
- `documentation.mdc` y `github-pages.mdc`: mantenimiento de esta documentación.

Varias reglas existen porque un error real las motivó: una convención de
unidades asumida sin verificar inflaba el ingreso de BESS 1000x; de ahí la regla
de verificar unidades contra el código antes de escribirlas en un spec.

## 3. Skills propias del repositorio

En [`.agents/skills/`](https://github.com/jccamargo94/gridforge/tree/develop/.agents/skills)
hay cuatro skills específicas de este proyecto, no genéricas:

| Skill | Qué automatiza |
|---|---|
| `gridforge-bug-reporter` | Recoge los detalles de un bug o feature y redacta un issue con las convenciones del repo (título con prefijo de área, cuerpo en español). |
| `gridforge-issues-resolver` | Lista issues abiertos, crea la rama desde `develop`, implementa, corre las compuertas reales (ruff, pytest, ty, lint/test del frontend) y abre el PR. |
| `gridforge-pr-reviewer` | Revisa un PR contra las convenciones propias (Pydantic v2, `Storage`, solver por defecto, dependencias) y los *gotchas* conocidos. |
| `documentation-maintainer` | Mantiene README, `AGENTS.md` y este sitio alineados con la implementación real. |

## 4. Límites declarados

- Los datos reales de XM no están en el repositorio (`data/` es git-ignored); los
  tests corren contra un fixture sintético (`tests/fixtures/xm_smoke/`). Que los
  tests pasen no implica que el modelo funcione con datos reales.
- No se refactoriza `case_builder.py` sin una prueba dorada previa.
- Las compuertas bloqueantes son `ruff` y `pytest`; `ty` es informativo.
