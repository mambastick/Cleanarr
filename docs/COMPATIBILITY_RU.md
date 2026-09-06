# Матрица совместимости

[English](COMPATIBILITY.md) · [Русский](COMPATIBILITY_RU.md)

Это публичный контракт совместимости для release candidate CleanArr 0.9 и
серии 1.x. Сервис считается поддерживаемым только после прохождения
автоматизированного gate для точной строки ниже; успешного подключения самого
по себе недостаточно для сертификации.

Последняя полная локальная сертификация: **2026-08-12**. Перед публикацией
каждого тега release workflow повторяет тот же digest-pinned gate на чистом
GitHub-hosted runner.

## Сертифицированные версии зависимостей

| Зависимость | Сертифицированная версия | Контракт API | Воспроизводимый fixture |
| --- | --- | --- | --- |
| qBittorrent | 5.2.3 | Web API v2; cookie login и определение версии | `lscr.io/linuxserver/qbittorrent:5.2.3_v2.0.14-ls471@sha256:6816d2b144b1eb97665f886e41e18a14d026ba78c9d0953fc68a1211ea819433` |
| Transmission, старое поколение | 4.0.6 | legacy RPC с session-ID negotiation и Basic auth | `lscr.io/linuxserver/transmission:4.0.6-r6-ls326@sha256:452310cb020c036d293e879698097acb6cc653db2676610bf8e3b58a3f4d2af5` |
| Transmission, новое поколение | 4.1.3 | JSON-RPC 2.0 с session-ID negotiation и Basic auth | `lscr.io/linuxserver/transmission:4.1.3-r0-ls357@sha256:81787bc706d3833d252e6d8b94545fea46bf2156f616320991a395619a477d2c` |
| Deluge | 2.2.0 | аутентифицированный Web JSON-RPC с подключённым daemon | `lscr.io/linuxserver/deluge:2.2.0-ls381@sha256:33a939576f7ecfc1227db1a0cb2afce030ce983e620ec9d93c956e3700e21fe9` |
| rTorrent | 0.16.17 | аутентифицированный HTTP XML-RPC | `crazymax/rtorrent-rutorrent:5.3.7-0.16.17@sha256:395f32ff75ab84a5615336829c4b846c154113129bc90b911c08a0f5261043f1` |
| Radarr | 6.3.0.10514 | API v3 | `lscr.io/linuxserver/radarr:version-6.3.0.10514@sha256:a45b5ab0f850f39edb4cc9c95bbd967b52ddc3d4574a4dfb45561177db6c88f4` |
| Sonarr | 4.0.19.2979 | API v3 | `lscr.io/linuxserver/sonarr:version-4.0.19.2979@sha256:373159ba768e23a3a1c497d9f2b936addf8fd5b1fdce7dd6a14080ac928bfda0` |
| Seerr | 3.4.1 | API v1 | `ghcr.io/seerr-team/seerr:v3.4.1@sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1` |
| Jellyfin | 10.11.11 | аутентифицированный server API | `jellyfin/jellyfin:10.11.11@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db` |

Fixture rTorrent содержит web frontend ruTorrent, но сертифицируется только
XML-RPC engine rTorrent. ruTorrent и Flood являются frontend, а не отдельными
download engines. Другие релизы, включая более новую upstream-версию rTorrent,
остаются вне контракта поддержки до добавления их точной версии в эту таблицу
вместе с зелёным gate.

## Что доказывает gate

Для каждой зависимости gate запускает новый изолированный сервис, проверяет
заявленную версию и аутентифицированный health-контракт и доказывает fail-closed
поведение при неверных credentials. Затем тест каждого torrent-клиента:

- создаёт реальную детерминированную раздачу через нативный API;
- читает один нормализованный snapshot и проверяет контракт его состояния,
  размера, progress и freshness;
- выполняет pause и resume через нативную обратимую команду, проверяет итоговое
  нормализованное состояние и доказывает идемпотентность повтора каждой команды;
- проверяет dry-run lookup без мутаций;
- удаляет запись раздачи без данных;
- считает повторное удаление идемпотентным отсутствием;
- повторно добавляет раздачу и выполняет удаление вместе с данными.

Основной обязательный suite дополняет live gate проверками BitTorrent v1/v2 и
hybrid identifiers, таймаутов, seeding policy, retry/partial failure,
pack/shared-path/cross-seed отказов, всех media item types, восстановления после
рестарта, duplicate events и одновременной multi-instance маршрутизации. Live
fixtures Radarr, Sonarr, Jellyfin и Seerr проверяют точные аутентифицированные
версии API и read-контракты, используемые этими сценариями.

Репетиция candidate проверяет оба направления на реальных выпущенных
контейнерах: `v0.2.11 -> candidate -> восстановленный v0.2.11`,
`v0.9.0 -> candidate -> восстановленный v0.9.0`,
`v1.0.0 -> candidate -> восстановленный v1.0.0` и последнюю stable
`v1.1.0 -> candidate -> восстановленный v1.1.0`. Проверяются верифицированный
backup, миграция схем БД/config, сохранность конфигурации и истории активности.
В пути v1.1.0 дополнительно восстанавливается автоматический sidecar schema v3,
созданный до записи candidate configuration schema 4 или database schema 6.

Полный локальный запуск из чистого checkout:

```bash
backend/.venv/bin/python compatibility/run.py
docker build --provenance=false -f deploy/Dockerfile -t cleanarr:compatibility-candidate .
backend/.venv/bin/python compatibility/rehearse_upgrade.py cleanarr:compatibility-candidate
```

Сервисы публикуют тестовые порты только на `127.0.0.1`, используют временные
volumes и удаляются после проверки. `CLEANARR_COMPAT_KEEP=1` допустим только для
локальной диагностики: он намеренно сохраняет stack и выводит сгенерированные
пути project/runtime.

Gate релиза 2.0.4 дополнительно проверяет последнюю стабильную версию по пути
`v2.0.3 -> candidate -> restored v2.0.3`: закреплённый опубликованный образ,
заполненные конфигурацию и историю, проверенный backup. Этот patch сохраняет
схему БД 6 и схему конфигурации 4.

## Граница совместимости 2.0

CleanArr v1.1.0 сертифицировал нормализованные Downloads reads и идемпотентный
mapping pause/resume для всех четырёх torrent adapters. Candidate v2.0 сохраняет
эти contracts без добавления destructive authority. Заявлять непрерывность
можно только после того, как из release commit пройдут этот точный pinned
profile, container/package smoke, репетиция backup/restore с последней stable
v1.1.0 до v6/config-v4, а также populated migration tests v5-to-v6 и
config-v3-to-v4.

Сам по себе profile **не** сертифицирует выполнение seeding-stop policy,
cleanup-candidate aggregation, first-run workflow или batch APIs. Успешная
проверка подключения, HTTP response или cached observation никогда не являются
evidence совместимости этих flows.

## Политика совместимости и deprecation серий 1.x и 2.x

- Точные строки выше являются проверенным support floor для 1.0. Совместимость
  с patch-релизом зависимости не заявляется молча: сначала его должен
  сертифицировать CI.
- CleanArr 2.0 сохраняет документированные webhook, configuration-export,
  database, adapter и fail-closed safety contracts серии 1.x. Major-версия
  обозначает новый production UI и authenticated-границу administrator/viewer;
  она не удаляет Tier 1 integration и не обходит объявленное deprecation window.
- CleanArr 2.x сохраняет обратную совместимость этих документированных
  contracts. Minor-релизы могут добавлять поля и ordered migrations.
- Планируемое удаление или несовместимое изменение объявляется на двух языках
  минимум за один minor-релиз CleanArr и за 90 дней до удаления.
- Устаревший configuration key остаётся читаемым в течение этого срока и
  мигрируется, если возможна миграция без потери данных.
- Критическая security- или data-loss-проблема может потребовать ускоренного
  удаления. Release notes обязаны назвать исключение, затронутые версии и
  безопасный путь миграции или rollback.
- Несовместимые изменения API/configuration вне security-исключения требуют
  новой major-версии CleanArr. Поддерживаемая версия зависимости никогда не
  удаляется молча.
