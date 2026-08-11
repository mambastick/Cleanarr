# Участие в разработке CleanArr

[English](CONTRIBUTING.md) · [Русский](CONTRIBUTING_RU.md)

Спасибо за интерес к проекту.

## Требования

- Python 3.12+
- Node.js 24+ и pnpm 10
- Docker для проверки контейнерного образа
- Хотя бы один поддерживаемый сервис для интеграционных проверок: Jellyfin, Radarr, Sonarr и т. п.

## Локальная разработка

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn cleanarr.api.app:app --reload
```

API будет доступен на `http://localhost:8000`.

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Dev-сервер проксирует `/api` на `http://localhost:8000`.

## Как внести изменение

1. Создайте fork и отдельную ветку от `main`.
2. Делайте небольшие и логически завершённые коммиты.
3. По возможности проверяйте изменение на реальных сервисах.
4. Откройте Pull Request в `main` и опишите причину и результат изменения.

## Стиль коммитов

Используйте [Conventional Commits](https://www.conventionalcommits.org):

```text
feat(scope): short description

Longer explanation if needed.
```

Основные scope: `backend`, `frontend`, `deploy`, `packaging`, `docs`.

## Ошибки и предложения

Для ошибки создайте [GitHub Issue](../../issues/new?template=bug_report.md) и приложите шаги воспроизведения, ожидаемое и фактическое поведение, логи и версии сервисов.

Для новой возможности создайте [GitHub Issue](../../issues/new?template=feature_request.md) с описанием сценария и предлагаемого решения.

## Стиль кода и проверки

- Python: `ruff format`, `ruff check`, `pytest`.
- TypeScript/TSX: Prettier при наличии конфигурации и проверка TypeScript.

Перед Pull Request должны успешно завершаться backend-тесты и `pnpm build`.

## Релизы

Каждый релиз содержит заметки на русском и английском языках. `.deb` и `.rpm` для `amd64` и `arm64` собираются из того же тега, что и контейнер. Порядок описан в [руководстве по релизу](docs/RELEASING_RU.md).
