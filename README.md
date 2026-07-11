# MixPilot

Ремиксы, соединение песен и каверы собственным голосом — Windows-приложение, всё аудио обрабатывается локально (RTX 3070). Проект **PRJ-2026-005** воркспейса PROJECT_OS.

Документация (источник истины):

- Продукт и план: `C:\TheIceBoys\PROJECT_OS\01_PROJECTS\ACTIVE\mixpilot\ROADMAP.md`
- UX/UI: `…\mixpilot\01_DOCS\UX_UI.md` · ТЗ: `…\01_DOCS\TZ.md` · Модели: `…\01_DOCS\MODELS.md`

## Архитектура

- `electron/` — main-процесс: окно, жизненный цикл Python-worker (`workerManager.cjs`), preload-мост.
- `src/` — React + TypeScript (Vite), дизайн-система «Aurora Noir» (`src/app/theme.css`).
- `worker/` — Python 3.11 + FastAPI на `127.0.0.1:<свободный порт>`; управляется через uv.
- `scripts/` — dev-обвязка под портативные Node/uv воркспейса `C:\TheIceBoys\TOOLS`.

## Запуск (dev)

```cmd
scripts\dev.cmd
```

Поднимает vite (порт 3520), Electron и Python-worker (первый запуск сам создаст `.venv` по `uv.lock`).

## Проверки

```cmd
call scripts\env.cmd
npm run typecheck   && rem типы UI
npm run test        && rem vitest
npm run ui:build    && rem прод-сборка UI
npm run smoke       && rem worker поднялся и ответил /meta (без окна)
cd worker && uv run pytest
```

## Правила

- Никаких музыкальных терминов в обязательном UI-пути; названия моделей пользователю не показываются.
- Аудио и голос не покидают компьютер; в облако (Claude API) уходит только текст — по тумблеру.
- `.cmd`/`.ps1` — только ASCII (ловушки кодировок Windows PowerShell 5.1).
