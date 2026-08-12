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
- прикладывает пакеты, SPDX JSON SBOM и `SHA256SUMS`;
- создаёт подписанные GitHub artifact attestations для release files и
  build/SBOM attestations для digest GHCR-образа.

Обязательный quality workflow завершается ошибкой при исправимых high/critical
уязвимостях dependencies или container, committed secrets и high/critical
ошибках deployment configuration, обнаруженных Trivy. Релиз нельзя публиковать
в обход красного scan.

## Проверка скачанных артефактов

```bash
sha256sum --check SHA256SUMS
gh attestation verify cleanarr_X.Y.Z_amd64.deb -R mambastick/Cleanarr
gh attestation verify oci://ghcr.io/mambastick/cleanarr:X.Y.Z -R mambastick/Cleanarr
```

Checksum подтверждает соответствие файла release manifest. Attestation
дополнительно связывает digest артефакта или образа с этим репозиторием,
коммитом и build identity GitHub Actions. SPDX JSON files в release assets
описывают dependency sets контейнера и native packages.

Не переносите и не пересоздавайте опубликованный тег. Для восстановления публикации артефактов используйте ручной запуск с существующим тегом и предварительно убедитесь, что версия исходного кода совпадает.

## Ручное восстановление артефактов

```bash
gh workflow run docker-release.yml \
  -f release_tag=vX.Y.Z \
  -f publish=true
```

Команда собирает нативные пакеты из текущей default-ветки. Используйте её только
если ветка всё ещё содержит точную версию приложения из тега. Manual recovery
не публикует контейнер повторно; сохраните и проверьте исходные attestations,
привязанные к его digest.
