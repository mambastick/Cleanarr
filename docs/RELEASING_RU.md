# Выпуск релиза

[English](RELEASING.md) · [Русский](RELEASING_RU.md)

Заметки каждого релиза CleanArr публикуются на русском и английском языках. Один тег выпускает multi-architecture контейнер и нативные DEB/RPM-пакеты из одного коммита.

## Подготовка

1. Измените версию в `backend/pyproject.toml` и `backend/src/cleanarr/api/app.py`.
2. Добавьте `docs/releases/vX.Y.Z.md` со строгой структурой:

```markdown
## Русский

### Изменения

- ...

## English

### Changes

- ...
```

3. Выполните backend-тесты, сборку frontend и Docker, а также smoke-тесты нативных пакетов.
4. Влейте релизный коммит в `main`.

## Публикация

```bash
git tag -a vX.Y.Z -m "CleanArr X.Y.Z"
git push origin main vX.Y.Z
```

После этого `.github/workflows/docker-release.yml`:

- собирает и публикует GHCR-образ для `linux/amd64` и `linux/arm64`;
- собирает DEB и RPM для `amd64` и `arm64` на нативных runner-ах;
- создаёт или обновляет GitHub Release из `docs/releases/vX.Y.Z.md`;
- прикладывает пакеты и `SHA256SUMS`.

Не переносите и не пересоздавайте опубликованный тег. Для восстановления публикации артефактов используйте ручной запуск с существующим тегом и предварительно убедитесь, что версия исходного кода совпадает.

## Ручное восстановление артефактов

```bash
gh workflow run docker-release.yml \
  -f release_tag=vX.Y.Z \
  -f publish=true
```

Команда собирает нативные пакеты из текущей default-ветки. Используйте её только если ветка всё ещё содержит точную версию приложения из тега.
