---
description: Corre los gates de validación de gridforge — ruff (lint+format), pytest, ty informativo y, si se tocó frontend, lint/test.
agent: build
---

Corre los gates de validación de gridforge y reporta cada resultado con conteos exactos:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run pytest -q`
4. `uv run ty check app/` — INFORMATIVO, nunca bloqueante (si falla, no lo trates como blocker)

$ARGUMENTS

Frontend (solo si el cambio tocó `frontend/`):
- `cd frontend && npm run lint`
- `cd frontend && npm run test`

Si alguno falla, no continúes como si estuviera verde: reporta el fallo y los pasos para
corregirlo. Recuerda: ruff y pytest son bloqueantes; `ty` no.
