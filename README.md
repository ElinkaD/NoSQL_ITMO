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

## Lab 1: Healthcheck (Python FastAPI)

Минимальный HTTP-сервис с одним endpoint `GET /health`.


## Конфигурация

Единственный конфигурационный файл: `.env.local`.

```env
APP_PORT=8080
```

## Запуск и проверка

```bash
make run
curl http://localhost:8080/health
# {"status":"ok"}
make stop
```
