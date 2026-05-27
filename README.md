# EventHub - NoSQL Database Project
[![EventHub](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml/badge.svg)](https://github.com/ElinkaD/NoSQL_ITMO/actions/workflows/eventhub.yml)

Backend-сервис платформы мероприятий для практического изучения NoSQL баз данных.

Проект развивается по этапам в рамках лабораторных работ и сохраняет совместимость с предыдущими версиями сервиса.

## Требования к реализации

- используется предоставленный шаблон репозитория [ndbx-template](https://github.com/sitnikovik/ndbx-template)
- соблюдаются требования к структуре проекта из [CONTRIBUTING.md](https://github.com/sitnikovik/ndbx-template?tab=contributing-ov-file)
- проект реализован на `python`
- каждая следующая лабораторная работа развивается поверх предыдущей
- новая функциональность не должна ломать предыдущие лабы

## Lab 5

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
- `POST /events/{event_id}/like`
- `POST /events/{event_id}/dislike`
- `POST /event/{event_id}/like`
- `POST /event/{event_id}/dislike`

### Возможности lab 5

- реакции на мероприятия хранятся в Cassandra
- счетчики реакций кэшируются в Redis по стратегии cache-aside
- `GET /events`, `GET /events/{id}`, `GET /users/{id}/events` поддерживают `?include=reactions`
- реакции агрегируются по названию мероприятия, а не только по одному `event_id`
- для одинакового `title` можно создавать несколько разных встреч на разное время
- для автогрейдера поддержан alias `POST /event/{event_id}/like|dislike`

## Lab 6

Текущая версия сервиса дополнительно реализует

- `POST /events/{event_id}/reviews`
- `GET /events/{event_id}/reviews`
- `PATCH /events/{event_id}/reviews/{review_id}`
- `GET /events`, `GET /events/{id}`, `GET /users/{id}/events` поддерживают `?include=reviews`

## Lab 7

Текущая версия сервиса дополнительно реализует

- `GET /recommendations`

### Возможности lab 7

- рекомендации мероприятий строятся по графу лайков в Neo4j
- рекомендации доступны только авторизованному пользователю и только для самого себя
- рекомендации кэшируются в Redis по стратегии cache-aside
- в рекомендациях не возвращаются мероприятия, которые пользователь уже лайкал
- если в рекомендации попадает несколько событий с одинаковым `title`, возвращается только ближайшее по `started_at`
- рекомендации сортируются по релевантности: от большего числа лайков к меньшему

## Совместимость с предыдущими лабами

Сервис сохраняет

- `GET /health` из lab 1
- механику анонимных Redis-сессий из lab 2
- регистрацию пользователей, login/logout и базовую работу с событиями из lab 3
- поиск, карточки и редактирование событий из lab 4
- реакции из lab 5
- отзывы и summary по ним из lab 6

Уточнения

- `GET /health` возвращает ровно `{"status":"ok"}`
- `GET /health` не создает сессию и не продлевает ttl
- `POST /session` создает новую сессию или продлевает существующую
- одинаковые названия событий теперь допустимы, потому что lab 5 требует агрегацию реакций по `title`

## Архитектура хранения

### Redis

Redis хранит

- сессии по ключам `sid:{session_id}`
- кэш счетчиков реакций по ключам `event:{md5(title)}:reactions`
- кэш агрегатов отзывов по ключам `event:{md5(title)}:reviews`
- кэш рекомендаций по ключам `user:{user_id}:recomms`

Внутри session hash хранятся

- `created_at`
- `updated_at`
- `user_id` если пользователь авторизован

В кэше реакций хранится JSON вида

```json
{
  "likes": 1,
  "dislikes": 0
}
```

В кэше отзывов хранится JSON вида

```json
{
  "count": 3,
  "rating": 4.7
}
```

В кэше рекомендаций в Redis hash хранится поле `events` со списком мероприятий в JSON

### MongoDB

Mongo используется в режиме sharded cluster

- `configReplSet`
- `shard1ReplSet`
- `shard2ReplSet`
- отдельный `mongos`

Коллекции

- `users`
- `events`

Коллекция `events` зашардирована по ключу `{ created_by: "hashed" }`.

### Cassandra

Cassandra используется как основное хранилище реакций.

Создается keyspace `CASSANDRA_KEYSPACE` и таблица `event_reactions`

- `event_id text`
- `created_by text`
- `like_value tinyint`
- `created_at timestamp`

Первичный ключ

- `PRIMARY KEY ((event_id), created_by)`

### Neo4j

Neo4j используется как граф рекомендаций.

Узлы

- `(:User {id})`
- `(:Event {id, title})`

Связи

- `(user)-[:LIKED]->(event)`

Граф обновляется при

- создании пользователя
- создании события
- постановке лайка

Дизлайки не удаляют связь `LIKED`, потому что lab 7 учитывает только сам факт лайка.

Также создаются secondary indexes по

- `created_by`
- `like_value`

Также создается таблица `event_reviews`

- `event_id text`
- `created_by text`
- `id uuid`
- `rating tinyint`
- `comment text`
- `created_at timestamp`
- `updated_at timestamp`

Первичный ключ

- `PRIMARY KEY ((event_id), created_by)`

## Конфигурация

Основной конфигурационный файл проекта это `.env.local`

```env
APP_HOST=localhost
APP_PORT=8080
APP_USER_SESSION_TTL=60
APP_LIKE_TTL=60
APP_EVENT_REVIEWS_TTL=120
APP_RECOMMENDATIONS_TTL=60

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

CASSANDRA_HOSTS=cassandra
CASSANDRA_PORT=9042
CASSANDRA_USERNAME=
CASSANDRA_PASSWORD=
CASSANDRA_KEYSPACE=testkeyspace
CASSANDRA_CONSISTENCY=ONE

NEO4J_URL=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

`MONGODB_USER` и `MONGODB_PASSWORD` используются приложением.

`MONGODB_APP_USER` и `MONGODB_APP_PASSWORD` создаются init-скриптом внутри кластера.

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

## Проверка хранилищ

Проверить список Mongo-шардов

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

Проверить статус Cassandra

```bash
docker compose --env-file .env.local exec -T cassandra \
  cqlsh -e "DESCRIBE KEYSPACES"
```

Проверить таблицу реакций

```bash
docker compose --env-file .env.local exec -T cassandra \
  cqlsh -e "DESCRIBE TABLE testkeyspace.event_reactions"
```

Проверить таблицу отзывов

```bash
docker compose --env-file .env.local exec -T cassandra \
  cqlsh -e "DESCRIBE TABLE testkeyspace.event_reviews"
```

Проверить граф Neo4j

```bash
docker compose --env-file .env.local exec -T neo4j \
  cypher-shell -a bolt://localhost:7687 -u neo4j -p password \
  "MATCH (n) RETURN labels(n), count(*)"
```

## Postman коллекция

Для проверки приложения используйте коллекцию

- [api/52399890-60f7994f-573a-4e39-8b98-ce0c23e4e595.json](/home/elina/itmo/NoSQL_ITMO/api/52399890-60f7994f-573a-4e39-8b98-ce0c23e4e595.json)

Коллекция покрывает

- сценарии lab 2 по `health` и `session`
- сценарии lab 3 по регистрации пользователей и авторизации
- сценарии lab 4 по поиску пользователей и событий
- сценарии lab 5 по реакциям и `include=reactions`
- сценарии lab 6 по отзывам и `include=reviews`
- сценарии lab 7 по рекомендациям и кэшу рекомендаций
- карточки пользователей и событий
- редактирование событий
- негативные сценарии `400`, `401`, `404`

## Примеры быстрых команд

```bash
curl -i http://localhost:8080/health

curl -i -X POST http://localhost:8080/session

curl -i -X POST http://localhost:8080/event/<event_id>/like \
  -H 'Cookie: X-Session-Id=<sid>'

curl -i "http://localhost:8080/events/<event_id>?include=reactions"

curl -i -X POST http://localhost:8080/events/<event_id>/reviews \
  -H 'Cookie: X-Session-Id=<sid>' \
  -H 'Content-Type: application/json' \
  -d '{"comment":"Отличное событие","rating":5}'

curl -i "http://localhost:8080/events/<event_id>/reviews?limit=10&offset=0"

curl -i "http://localhost:8080/events/<event_id>?include=reactions,reviews"

curl -i http://localhost:8080/recommendations \
  -H 'Cookie: X-Session-Id=<sid>'
```
