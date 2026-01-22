# Local Data Search System (AI Assisted)

Проект реализует быстрый поиск и расчёт времени сборки по наименованиям без тяжёлого RAG. ИИ (Ollama) используется только для формирования «красивого» отчёта.

## Архитектура
- **PostgreSQL** хранит дерево данных (проекты → шкафы → позиции → вид номенклатуры → этапы).
- **Python + FastAPI** выполняет поиск, сопоставление и расчёт времени.
- **Ollama** локально форматирует отчёт.

## Быстрый старт
1) Установите зависимости:
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Создайте БД и примените схему:
```
psql -d assembly -f app/db/schema.sql
```

3) При загрузке данных заполняйте `items.name_norm` нормализованной строкой
   (нижний регистр, удаление лишних символов, `ё` → `е`). Это ускоряет поиск.

4) Импорт CSV (пример):
```
python scripts/import_csv.py --path "Маленький пример большой таблицы .csv" --stage-times stage_times.json --default-time 0
```
`stage_times.json` — словарь вида `{ "Сборка корпуса": 30, "Дополнительные работы": 10 }`.
Если в CSV есть столбец `Шаблон врмени в минутах`, он имеет приоритет над JSON и `default-time`,
и сохраняется **в каждой позиции** (`items.assembly_time_minutes`).
Дополнительно можно включить контроль импорта:
```
python scripts/import_csv.py --path "Маленький пример большой таблицы .csv" --error-report import_errors.csv --strict
```
Для статистики импорта:
```
python scripts/import_csv.py --path "Маленький пример большой таблицы .csv" --stats-out import_stats.json
```

5) Настройте переменные окружения:
```
cp .env.example .env
```

6) Запуск API:
```
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Запуск в Docker

1) Собрать и запустить контейнеры:
```
docker compose up --build
```

2) Применить схему БД:
```
docker compose exec db psql -U assembly -d assembly -f /app/app/db/schema.sql
```

3) Импорт CSV (пример):
```
docker compose exec app python scripts/import_csv.py --path "Маленький пример большой таблицы .csv" --stats-out import_stats.json
```

Примечание: Ollama запускается как отдельный контейнер `ollama`.
Если модель ещё не загружена, выполните:
```
docker compose exec ollama ollama pull qwen2.5:3b
```

## Пример запроса
```
POST /v1/estimate
{
  "names": ["Щит вводной 3ф 25А", "Шкаф управления насосом"],
  "format_report": true,
  "project_code": "проект123",
  "cabinet_code": "шкаф111"
}
```

## Веб‑интерфейс

Откройте в браузере:
```
http://localhost:8000
```
Функции: список чатов, новый чат, переключение режимов, история сообщений,
ввод наименований и просмотр суммарных результатов.

## Интерактивный чат
Эндпоинт для чата:
```
POST /v1/chat
{
  "message": "Посчитай время на сборку",
  "names": ["Щит вводной 3ф 25А", "Шкаф управления насосом"],
  "history": [],
  "project_code": "проект123",
  "cabinet_code": "шкаф111",
  "mode": "auto"
}
```
`mode` управляет режимом работы:
- `auto` — поиск только если переданы `names`
- `chat` — всегда только диалог, без поиска
- `estimate` — всегда поиск и расчет (даже если `names` пусты)

## Что дальше
- Загрузить данные в таблицы.
- Добавить словарь сокращений (если нужно).
- Настроить индексы и, при необходимости, pg_trgm.
