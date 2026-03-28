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

## Lab 3: Users and Events on MongoDB

Текущая версия сервиса реализует:

- `GET /health` для проверки работоспособности;
- `POST /session` для создания и продления анонимной сессии в Redis;
- `POST /users` для регистрации пользователя с bcrypt-хэшем пароля;
- `POST /auth/login` для входа пользователя в существующую или новую сессию;
- `POST /auth/logout` для удаления текущей сессии и cookie;
- `POST /events` для создания событий авторизованным пользователем;
- `GET /events` для просмотра событий с фильтрацией по `title` и пагинацией через `limit`/`offset`.

Хранилища:

- Redis хранит сессии по ключу `sid:{session_id}` и, при авторизации, поле `user_id`;
- MongoDB хранит коллекции `users` и `events` с индексами, требуемыми лабораторной работой.

## Совместимость с Lab 2

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
MONGODB_DATABSE=eventhub
MONGODB_USER=eventhub
MONGODB_PASSWORD=eventhub
MONGODB_HOST=mongodb
MONGODB_PORT=27017
```

## Запуск и проверка

```bash
make run

curl -i http://localhost:8080/health

curl -i -X POST http://localhost:8080/session

curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  -d '{"full_name":"John Doe","username":"jdoe","password":"strong-pass"}'

curl -i -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"jdoe","password":"strong-pass"}'

make stop
```

Postman-коллекция лежит в `api/52399890-5f7a1e89-9e19-4ffa-9894-10161ccf2f5a.json`. В ней есть сценарии для (пока без доработок по 3 лабе):
- `health` без cookie;
- `health` с валидной, невалидной и истекшей cookie;
- создания новой сессии;
- обновления существующей сессии;
- повторного создания сессии после истечения TTL.
