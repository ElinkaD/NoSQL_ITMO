# EventHub - NoSQL Database Project
[![EventHub](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml/badge.svg)](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml)

Backend-сервис платформы мероприятий для практического изучения NoSQL баз данных. Проект выполняется поэтапно в рамках лабораторных работ и представляет собой единый сервис, который развивается в течение всего курса.

## Требования к реализации

- Используется предоставленный шаблон репозитория
[ndbx-template](https://github.com/sitnikovik/ndbx-template)
- Соблюдаются требования к структуре проекта, описанные в
[CONTRIBUTING.md](https://github.com/sitnikovik/ndbx-template?tab=contributing-ov-file)
- Выполняется на **Python**
- Все лабораторные работы должны полностью проходить
автоматическую проверку в GitHub Actions
- Каждая последующая лабораторная работа должна
на основе предыдущей
- Очередная лабораторная работа не должна ломать
функциональность предыдущих лабораторных работ
(проверяется в процессе автоматической проверки)

## Lab 2: Anonymous Sessions on Redis

Сервис реализует:

- `GET /health` для проверки работоспособности;
- `POST /session` для создания и продления анонимной сессии;
- хранение сессий в Redis с TTL по ключу `sid:{session_id}`.

Уточнение условий лабы 2:

- `GET /health` всегда возвращает ровно `{"status":"ok"}`;
- `GET /health` не создаёт сессию и не обновляет TTL;
- `GET /health` добавляет `Set-Cookie` только если в запросе пришла валидная cookie и такая сессия реально существует в Redis;
- первый `POST /session` возвращает `201 Created`, пустое тело и новую cookie `X-Session-Id`;
- повторный `POST /session` с живой сессией возвращает `200 OK`, пустое тело, тот же `sid` и обновляет TTL;
- если cookie невалидна или сессия уже истекла, `POST /session` создаёт новую сессию и возвращает `201 Created`.


## Конфигурация

Единственный конфигурационный файл: `.env.local`.

```env
APP_HOST=localhost
APP_PORT=8080
APP_USER_SESSION_TTL=60
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

## Запуск и проверка

```bash
make run

curl -i http://localhost:8080/health

curl -i -X POST http://localhost:8080/session

make stop
```

Postman-коллекция лежит в `api/52399890-5f7a1e89-9e19-4ffa-9894-10161ccf2f5a.json`. В ней есть сценарии для:
- `health` без cookie;
- `health` с валидной, невалидной и истекшей cookie;
- создания новой сессии;
- обновления существующей сессии;
- повторного создания сессии после истечения TTL.
