# CODE_GUIDE

Короткая навигация по коду и связям между модулями.

## Карта модулей

- `app/main.py` — точка входа FastAPI, собирает приложение.
- `app/api/routes.py` — HTTP‑эндпоинты (`/v1/estimate`, `/v1/chat`).
- `app/core/config.py` — загрузка настроек из `.env`.
- `app/core/logging.py` — базовая настройка логов.
- `app/db/session.py` — подключение к БД и выдача `AsyncSession`.
- `app/db/schema.sql` — схема БД и индексы.
- `app/models/schemas.py` — Pydantic‑схемы запросов/ответов.
- `app/repositories/items.py` — SQL‑запросы к `items` и связанным таблицам.
- `app/services/estimation.py` — основной алгоритм поиска и расчёта времени.
- `app/services/matching.py` — fuzzy‑ранжирование кандидатов.
- `app/services/ollama.py` — генерация текста через локальную Ollama.
- `app/utils/normalization.py` — нормализация строк.
- `scripts/import_csv.py` — импорт CSV в БД + контроль качества и статистика.

## Ключевые потоки

### 1) Расчёт времени (API)

```
POST /v1/estimate
  -> app/api/routes.py
      -> app/services/estimation.py
          -> app/repositories/items.py
              -> БД (items + joins)
      -> app/services/ollama.py (опционально, если format_report=true)
```

### 2) Интерактивный чат

```
POST /v1/chat
  -> app/api/routes.py
      -> режим chat / estimate / auto
      -> estimation.py (если нужно искать)
      -> ollama.py (формирование ответа)
```

### 3) Импорт CSV

```
python scripts/import_csv.py
  -> normalize_text()
  -> upsert projects/cabinets/stages/types/items
  -> error_report (CSV) + stats (JSON)
```

## Где что править

- Логика поиска и агрегации: `app/services/estimation.py`
- Алгоритм fuzzy‑сопоставления: `app/services/matching.py`
- SQL‑выборки и фильтры: `app/repositories/items.py`
- Промпты и Ollama: `app/services/ollama.py`
- Схема таблиц и индексы: `app/db/schema.sql`
- Импорт CSV: `scripts/import_csv.py`

## Быстрые подсказки

- Хочешь изменить режим чата — смотри `ChatRequest.mode` в `app/models/schemas.py`.
- Нужен фильтр по проекту/шкафу — он уже есть в `repositories/items.py`.
- Время хранится в `items.assembly_time_minutes`, этапы без времени.
- Логи импорта: `--error-report`, статистика: `--stats-out`.
