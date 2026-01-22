"""Импорт CSV в PostgreSQL с нормализацией и контролем качества."""  # основной скрипт

import argparse  # CLI аргументы
import asyncio  # запуск async
import csv  # чтение CSV
import json  # работа с JSON
import os  # системные пути
import sys  # sys.path
from pathlib import Path  # пути
from typing import Dict, Optional, cast, List, Any  # типы

import asyncpg  # type: ignore  # драйвер PostgreSQL

ROOT = Path(__file__).resolve().parents[1]  # корень проекта
sys.path.append(str(ROOT))  # добавляем в sys.path

from app.core.config import settings  # noqa: E402  # настройки
from app.utils.normalization import normalize_text  # noqa: E402  # нормализация


HEADER_ALIASES = {  # маппинг заголовков CSV
    "Проект": "project",
    "Шкаф": "cabinet",
    "Артикул": "article",
    "Наименование": "name",
    "Вид номенклатуры": "nomenclature_type",
    "Название этапа": "stage",
    "Шаблон врмени в минутах": "stage_time_minutes",
}


def _normalize_db_url(url: str) -> str:
    """Приводит URL к формату, понятному asyncpg."""  # asyncpg не понимает SQLAlchemy URL
    return url.replace("postgresql+asyncpg://", "postgresql://")  # заменяем префикс


def _load_stage_times(path: Optional[str]) -> Dict[str, int]:
    """Загружает справочник времени этапов из JSON."""  # этап -> минуты
    if not path:
        return {}  # нет файла
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)  # читаем JSON
    return {str(k): int(v) for k, v in data.items()}  # приводим к int


async def _get_or_create_project(conn: asyncpg.Connection, code: str, cache: Dict[str, int]) -> int:
    """Получает или создаёт проект."""  # upsert по проекту
    if code in cache:
        return cache[code]  # быстрый путь
    project_id = await conn.fetchval(
        """
        INSERT INTO projects(project_code)
        VALUES($1)
        ON CONFLICT (project_code) DO UPDATE SET project_code = EXCLUDED.project_code
        RETURNING id
        """,
        code,
    )
    cache[code] = project_id  # кешируем
    return project_id  # id проекта


async def _get_or_create_cabinet(
    conn: asyncpg.Connection,
    project_id: int,
    cabinet_code: str,
    cache: Dict[tuple, int],
) -> int:
    """Получает или создаёт шкаф внутри проекта."""  # upsert по шкафу
    key = (project_id, cabinet_code)  # ключ кеша
    if key in cache:
        return cache[key]  # быстрый путь
    cabinet_id = await conn.fetchval(
        """
        INSERT INTO cabinets(project_id, cabinet_code)
        VALUES($1, $2)
        ON CONFLICT (project_id, cabinet_code)
        DO UPDATE SET cabinet_code = EXCLUDED.cabinet_code
        RETURNING id
        """,
        project_id,
        cabinet_code,
    )
    cache[key] = cabinet_id  # кешируем
    return cabinet_id  # id шкафа


async def _get_or_create_stage(
    conn: asyncpg.Connection,
    stage_name: str,
    stage_time: Optional[int],
    default_time: int,
    stage_times: Dict[str, int],
    cache: Dict[str, int],
) -> int:
    """Получает или создаёт этап по названию."""  # этап без времени
    if stage_name in cache:
        return cache[stage_name]  # быстрый путь
    stage_id = await conn.fetchval(
        """
        INSERT INTO stages(stage_name)
        VALUES($1)
        ON CONFLICT (stage_name) DO NOTHING
        RETURNING id
        """,
        stage_name,
    )
    if stage_id is None:
        stage_id = await conn.fetchval(
            "SELECT id FROM stages WHERE stage_name = $1",
            stage_name,
        )
    cache[stage_name] = stage_id  # кешируем
    return stage_id  # id этапа


async def _get_or_create_nomenclature_type(
    conn: asyncpg.Connection,
    type_name: str,
    stage_id: int,
    cache: Dict[str, int],
) -> int:
    """Получает или создаёт вид номенклатуры."""  # upsert по виду
    if type_name in cache:
        return cache[type_name]  # быстрый путь
    type_id = await conn.fetchval(
        """
        INSERT INTO nomenclature_types(type_name, stage_id)
        VALUES($1, $2)
        ON CONFLICT (type_name) DO UPDATE SET stage_id = EXCLUDED.stage_id
        RETURNING id
        """,
        type_name,
        stage_id,
    )
    cache[type_name] = type_id  # кешируем
    return type_id  # id вида


async def _upsert_item(
    conn: asyncpg.Connection,
    cabinet_id: int,
    nomenclature_type_id: int,
    article: str,
    name: str,
    name_norm: str,
    assembly_time_minutes: int,
) -> None:
    """Вставляет или обновляет позицию по уникальному артикулу."""  # UPSERT по артикулу
    await conn.execute(
        """
        INSERT INTO items(cabinet_id, nomenclature_type_id, article, name, name_norm, assembly_time_minutes)
        VALUES($1, $2, $3, $4, $5, $6)
        ON CONFLICT (article)
        DO UPDATE SET
            cabinet_id = EXCLUDED.cabinet_id,
            nomenclature_type_id = EXCLUDED.nomenclature_type_id,
            name = EXCLUDED.name,
            name_norm = EXCLUDED.name_norm,
            assembly_time_minutes = EXCLUDED.assembly_time_minutes
        """,
        cabinet_id,
        nomenclature_type_id,
        article,
        name,
        name_norm,
        assembly_time_minutes,
    )


async def import_csv(
    path: str,
    stage_times_path: Optional[str],
    default_time: int,
    error_report_path: Optional[str],
    stats_out_path: Optional[str],
    strict: bool,
    incremental: bool,
) -> None:
    """Основная процедура импорта CSV."""  # основной сценарий
    db_url = _normalize_db_url(settings.database_url)  # приводим URL
    stage_times = _load_stage_times(stage_times_path)  # загружаем справочник
    existing_articles: set = set()  # артикулы уже в БД

    project_cache: Dict[str, int] = {}  # кеш проектов
    cabinet_cache: Dict[tuple, int] = {}  # кеш шкафов
    stage_cache: Dict[str, int] = {}  # кеш этапов
    type_cache: Dict[str, int] = {}  # кеш видов

    processed = 0  # обработано строк
    skipped = 0  # пропущено строк
    missing_time = 0  # время отсутствует/0
    invalid_time = 0  # некорректное время
    missing_required = 0  # нет обязательных полей
    duplicate_articles = 0  # конфликты артикулов

    seen_articles: Dict[str, Dict[str, str]] = {}  # для конфликтов артикула
    error_rows: List[Dict[str, Any]] = []  # проблемные строки
    stats_projects: Dict[str, int] = {}  # статистика проектов
    stats_cabinets: Dict[str, int] = {}  # статистика шкафов
    stats_stages: Dict[str, int] = {}  # статистика этапов
    stats_types: Dict[str, int] = {}  # статистика видов

    def add_error(reason: str, raw_row: Dict[str, Any], row_number: int) -> None:
        """Сохраняет проблемную строку в отчёт."""  # собираем ошибки
        error_rows.append({"row_number": row_number, "reason": reason, **raw_row})  # пишем строку

    async with asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5) as pool:  # пул соединений
        async with pool.acquire() as conn:  # одно соединение
            if incremental:  # инкрементальный импорт
                rows = await conn.fetch("SELECT article FROM items")  # загружаем артикулы из БД
                existing_articles = {row["article"] for row in rows}  # создаём множество
                print(f"Инкрементальный режим: уже в БД {len(existing_articles)} артикулов")
            
            with open(path, "r", encoding="utf-8") as file:  # CSV файл
                reader = csv.DictReader(file, delimiter=";")  # парсер CSV
                for row_number, row in enumerate(reader, start=2):  # со 2 строки
                    mapped = {}
                    for k, v in row.items():
                        if not k:
                            continue
                        key = k.strip().lstrip("\ufeff")  # убираем BOM и пробелы
                        mapped[HEADER_ALIASES.get(key, key)] = v.strip()

                    project_code = mapped.get("project")
                    cabinet_code = mapped.get("cabinet")
                    article = mapped.get("article")
                    name = mapped.get("name")
                    nom_type = mapped.get("nomenclature_type")
                    stage = mapped.get("stage")
                    stage_time_raw = mapped.get("stage_time_minutes")

                    if not all([project_code, cabinet_code, article, name, nom_type, stage]):  # обязательные поля
                        missing_required += 1
                        skipped += 1
                        add_error("missing_required_fields", mapped, row_number)
                        if strict:
                            raise RuntimeError("Строка без обязательных полей")
                        continue

                    project_code = cast(str, project_code)  # типизация
                    cabinet_code = cast(str, cabinet_code)
                    article = cast(str, article)
                    name = cast(str, name)
                    nom_type = cast(str, nom_type)
                    stage = cast(str, stage)

                    if incremental and article in existing_articles:  # уже в БД
                        skipped += 1
                        continue

                    name_norm = normalize_text(name)  # нормализация

                    stage_time = None
                    if stage_time_raw:
                        try:
                            stage_time = int(stage_time_raw)
                        except ValueError:
                            stage_time = None
                            invalid_time += 1  # счётчик
                            add_error("invalid_time_value", mapped, row_number)
                            if strict:
                                raise RuntimeError("Некорректное значение времени")

                    prev = seen_articles.get(article)  # проверка артикула
                    if prev:
                        if prev.get("name") != name or prev.get("stage") != stage:
                            duplicate_articles += 1
                            add_error("duplicate_article_conflict", mapped, row_number)
                            if strict:
                                raise RuntimeError("Конфликт по артикулу")
                    else:
                        seen_articles[article] = {"name": name, "stage": stage}

                    project_id = await _get_or_create_project(conn, project_code, project_cache)  # проект
                    cabinet_id = await _get_or_create_cabinet(conn, project_id, cabinet_code, cabinet_cache)  # шкаф
                    stage_id = await _get_or_create_stage(  # этап
                        conn,
                        stage,
                        stage_time,
                        default_time,
                        stage_times,
                        stage_cache,
                    )
                    type_id = await _get_or_create_nomenclature_type(conn, nom_type, stage_id, type_cache)  # вид

                    if stage_time is None:
                        stage_time = stage_times.get(stage, default_time)
                        if stage_time == 0:
                            missing_time += 1  # счётчик
                            add_error("missing_time_zero", mapped, row_number)
                            if strict:
                                raise RuntimeError("Отсутствует время этапа")

                    await _upsert_item(  # вставка позиции
                        conn,
                        cabinet_id,
                        type_id,
                        article,
                        name,
                        name_norm,
                        stage_time,
                    )

                    processed += 1  # всего обработано
                    stats_projects[project_code] = stats_projects.get(project_code, 0) + 1
                    stats_cabinets[cabinet_code] = stats_cabinets.get(cabinet_code, 0) + 1
                    stats_stages[stage] = stats_stages.get(stage, 0) + 1
                    stats_types[nom_type] = stats_types.get(nom_type, 0) + 1
                    if processed % 1000 == 0:
                        print(f"Импортировано строк: {processed}")  # прогресс

    print(f"Готово. Всего обработано строк: {processed}")  # финал
    if skipped > 0 or missing_time > 0 or invalid_time > 0 or duplicate_articles > 0:  # проблемы
        print(
            "Проблемы с временем: "
            f"нет/0 значений={missing_time}, некорректных значений={invalid_time}"
        )
        print(
            "Прочие проблемы: "
            f"пропущено строк={skipped}, дубликаты артикула={duplicate_articles}"
        )

    print("Статистика:")  # краткий итог
    print(f"- проектов: {len(stats_projects)}")  # уникальные проекты
    print(f"- шкафов: {len(stats_cabinets)}")  # уникальные шкафы
    print(f"- видов номенклатуры: {len(stats_types)}")  # уникальные виды
    print(f"- этапов: {len(stats_stages)}")  # уникальные этапы

    if error_report_path and error_rows:
        with open(error_report_path, "w", encoding="utf-8", newline="") as report:
            fieldnames = sorted({key for row in error_rows for key in row.keys()})
            writer = csv.DictWriter(report, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(error_rows)
        print(f"Отчёт об ошибках: {error_report_path}")  # путь к отчёту

    if stats_out_path:
        stats_payload = {
            "processed": processed,
            "skipped": skipped,
            "missing_time_zero": missing_time,
            "invalid_time": invalid_time,
            "missing_required": missing_required,
            "duplicate_articles": duplicate_articles,
            "projects_count": len(stats_projects),
            "cabinets_count": len(stats_cabinets),
            "types_count": len(stats_types),
            "stages_count": len(stats_stages),
            "top_projects": sorted(stats_projects.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_cabinets": sorted(stats_cabinets.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_types": sorted(stats_types.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_stages": sorted(stats_stages.items(), key=lambda x: x[1], reverse=True)[:10],
        }
        with open(stats_out_path, "w", encoding="utf-8") as stats_file:
            json.dump(stats_payload, stats_file, ensure_ascii=False, indent=2)  # пишем JSON
        print(f"Статистика: {stats_out_path}")  # путь к статистике


def parse_args() -> argparse.Namespace:
    """Читает параметры CLI."""  # аргументы командной строки
    parser = argparse.ArgumentParser(description="Импорт CSV в БД проекта")  # описание
    parser.add_argument("--path", required=True, help="Путь к CSV файлу")  # путь к CSV
    parser.add_argument("--stage-times", help="JSON файл вида {\"Название этапа\": 30}")  # справочник
    parser.add_argument("--default-time", type=int, default=0, help="Время по умолчанию, если этап не найден в JSON")  # fallback
    parser.add_argument("--error-report", help="Путь для CSV отчёта об ошибках")  # ошибки
    parser.add_argument("--stats-out", help="Путь для JSON статистики импорта")  # статистика
    parser.add_argument("--strict", action="store_true", help="Останавливать импорт при первой ошибке")  # строгий режим
    parser.add_argument("--incremental", action="store_true", help="Импортировать только новые артикулы (не обновлять)")  # инкремент
    return parser.parse_args()  # готовые аргументы


if __name__ == "__main__":
    args = parse_args()  # читаем аргументы
    asyncio.run(  # запускаем асинхронный импорт
        import_csv(
            args.path,
            args.stage_times,
            args.default_time,
            args.error_report,
            args.stats_out,
            args.strict,
            args.incremental,
        )
    )
