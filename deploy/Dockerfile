FROM node:24-bookworm-slim AS frontend-build

WORKDIR /app/frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend /app/frontend
RUN pnpm build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin cleanarr

COPY backend/pyproject.toml README.md /app/
COPY backend/src /app/src
COPY --from=frontend-build /app/src/cleanarr/ui/static /app/src/cleanarr/ui/static

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

USER cleanarr

EXPOSE 8089

CMD ["uvicorn", "cleanarr.main:app", "--host", "0.0.0.0", "--port", "8089"]
