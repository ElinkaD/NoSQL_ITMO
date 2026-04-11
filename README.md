# EventHub - NoSQL Database Project
[![EventHub](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml/badge.svg)](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml)

Backend-сервис платформы мероприятий для практического изучения NoSQL баз данных

Проект развивается по этапам в рамках лабораторных работ и сохраняет совместимость с предыдущими версиями сервиса

## Требования к реализации

- используется предоставленный шаблон репозитория [ndbx-template](https://github.com/sitnikovik/ndbx-template)
- соблюдаются требования к структуре проекта из [CONTRIBUTING.md](https://github.com/sitnikovik/ndbx-template?tab=contributing-ov-file)
- проект реализован на python
- каждая следующая лабораторная работа развивается поверх предыдущей
- новая функциональность не должна ломать lab 1 lab 2 и lab 3

## Lab 4

Текущая версия сервиса реализует

- `GET /health`
- `POST /session`
- `POST /users`
- `GET /users`
- `GET /users/{id}`
- `GET /users/{id}/events`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /events`
- `GET /events`
- `GET /events/{id}`
- `PATCH /events/{id}`

### Возможности lab 4

- поиск мероприятий по `title` `id` `category` `price_from` `price_to` `city` `date_from` `date_to` `user`
- редактирование мероприятия только его организатором
- поиск организаторов по `id` `name` с `limit` и `offset`
- просмотр карточки организатора
- просмотр списка мероприятий конкретного организатора
- шардирование `events` по хэшированному ключу `created_by`
- репликация mongo через replica set

## Совместимость с предыдущими лабами

Сервис сохраняет

- `GET /health` из lab 1
- механику анонимных redis сессий из lab 2
- регистрацию пользователей login logout и базовую работу с событиями из lab 3

Уточнения по lab 2

- `GET /health` возвращает ровно `{"status":"ok"}`
- `GET /health` не создает сессию и не продлевает ttl
- `POST /session` создает новую сессию или продлевает существующую

## Архитектура хранения

### Redis

Redis хранит сессии по ключам `sid:{session_id}`

Внутри hash хранятся

- `created_at`
- `updated_at`
- `user_id` если пользователь авторизован

### MongoDB

Mongo используется в режиме sharded cluster

- `configReplSet`
- `shard1ReplSet`
- `shard2ReplSet`
- отдельный `mongos`

Коллекции

- `users`
- `events`

Коллекция `events` зашардирована по ключу `{ created_by: "hashed" }`

## Конфигурация

Основной конфигурационный файл проекта это `.env.local`

```env
APP_HOST=localhost
APP_PORT=8080
APP_USER_SESSION_TTL=60

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=rediselina2003
REDIS_DB=0
REDIS_SOCKET_CONNECT_TIMEOUT=2
REDIS_SOCKET_TIMEOUT=2

MONGODB_DATABASE=eventhub
MONGODB_USER=
MONGODB_PASSWORD=
MONGODB_HOST=mongos
MONGODB_PORT=27017
MONGODB_APP_USER=eventhub
MONGODB_APP_PASSWORD=eventhub
MONGODB_SERVER_SELECTION_TIMEOUT_MS=2000
MONGODB_CONNECT_TIMEOUT_MS=2000
MONGODB_SOCKET_TIMEOUT_MS=2000
```

`MONGODB_USER` и `MONGODB_PASSWORD` используются приложением

`MONGODB_APP_USER` и `MONGODB_APP_PASSWORD` создаются init-скриптом внутри кластера

## Запуск

```bash
make run
make services
```

Остановка

```bash
make stop
```

Полная очистка контейнеров и volume

```bash
make clean
```

## Проверка кластера Mongo

Проверить список шардов

```bash
docker compose --env-file .env.local exec -T mongos \
  mongosh --quiet --port 27017 \
  --eval 'db.adminCommand({ listShards: 1 })'
```

Проверить что `events` зашардирована

```bash
docker compose --env-file .env.local exec -T mongos \
  mongosh --quiet --port 27017 \
  --eval 'db.getSiblingDB("config").collections.findOne({ _id: "eventhub.events" })'
```

Проверить replica set одного из шардов

```bash
docker compose --env-file .env.local exec -T shard1-01 \
  mongosh --quiet --port 27118 \
  --eval 'rs.status()'
```

## Postman коллекция

Для проверки приложения используйте коллекцию

- [api/52399890-lab4-3f0f7c5a-collection.json](/home/elina/itmo/NoSQL_ITMO/api/52399890-lab4-3f0f7c5a-collection.json)

Коллекция покрывает

- сценарии lab 2 по `health` и `session`
- сценарии lab 3 по регистрации пользователей и авторизации
- сценарии lab 4 по поиску пользователей и событий
- карточки пользователей и событий
- редактирование событий
- негативные сценарии `400` `401` `404`

## Примеры быстрых команд

```bash
curl -i http://localhost:8080/health

curl -i -X POST http://localhost:8080/session

curl -i -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"elina","password":"elina2003"}'
```
