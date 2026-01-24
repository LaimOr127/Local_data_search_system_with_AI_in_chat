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
    "Код вида номенклатуры": "nomenclature_type_code",
    "Вид номенклатуры": "nomenclature_type",
    "Колличество в 1 изделии": "quantity_per_unit",
    "Итоговое колличество": "total_quantity",
    "Название этапа": "stage_code",
    "Наименование операции": "operation_name",
    "Шаблон времени в минутах": "time_template_minutes",
}


def _normalize_db_url(url: str) -> str:
    """Приводит URL к формату, понятному asyncpg."""  # asyncpg не понимает SQLAlchemy URL
    return url.replace("postgresql+asyncpg://", "postgresql://")  # заменяем префикс


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
    stage_code: int,
    cache: Dict[int, int],
) -> int:
    """Получает или создаёт этап по коду."""  # этап по числовому коду
    if stage_code in cache:
        return cache[stage_code]  # быстрый путь
    stage_id = await conn.fetchval(
        """
        INSERT INTO stages(stage_code, stage_name)
        VALUES($1, $2)
        ON CONFLICT (stage_code) DO UPDATE SET stage_name = EXCLUDED.stage_name
        RETURNING id
        """,
        stage_code,
        f"Этап {stage_code}",  # название по умолчанию
    )
    cache[stage_code] = stage_id  # кешируем
    return stage_id  # id этапа


async def _get_or_create_nomenclature_type(
    conn: asyncpg.Connection,
    type_code: int,
    type_name: str,
    stage_id: int,
    cache: Dict[tuple, int],
) -> int:
    """Получает или создаёт вид номенклатуры."""  # upsert по виду
    key = (type_code, type_name)  # ключ кеша
    if key in cache:
        return cache[key]  # быстрый путь
    type_id = await conn.fetchval(
        """
        INSERT INTO nomenclature_types(type_code, type_name, stage_id)
        VALUES($1, $2, $3)
        ON CONFLICT (type_code, type_name) DO UPDATE SET stage_id = EXCLUDED.stage_id
        RETURNING id
        """,
        type_code,
        type_name,
        stage_id,
    )
    cache[key] = type_id  # кешируем
    return type_id  # id вида


async def _get_or_create_operation(
    conn: asyncpg.Connection,
    nomenclature_type_id: int,
    operation_code: int,
    operation_name: str,
    time_template_minutes: int,
    cache: Dict[tuple, int],
) -> int:
    """Получает или создаёт операцию."""  # upsert по операции
    key = (nomenclature_type_id, operation_code, operation_name)  # ключ кеша
    if key in cache:
        return cache[key]  # быстрый путь
    operation_id = await conn.fetchval(
        """
        INSERT INTO operations(nomenclature_type_id, operation_code, operation_name, time_template_minutes)
        VALUES($1, $2, $3, $4)
        ON CONFLICT (nomenclature_type_id, operation_code, operation_name)
        DO UPDATE SET time_template_minutes = EXCLUDED.time_template_minutes
        RETURNING id
        """,
        nomenclature_type_id,
        operation_code,
        operation_name,
        time_template_minutes,
    )
    cache[key] = operation_id  # кешируем
    return operation_id  # id операции


async def _upsert_item(
    conn: asyncpg.Connection,
    cabinet_id: int,
    nomenclature_type_id: int,
    operation_id: int,
    article: str,
    name: str,
    name_norm: str,
    quantity_per_unit: int,
    total_quantity: int,
) -> None:
    """Вставляет или обновляет позицию по уникальному артикулу."""  # UPSERT по артикулу
    await conn.execute(
        """
        INSERT INTO items(
            cabinet_id, nomenclature_type_id, operation_id,
            article, name, name_norm,
            quantity_per_unit, total_quantity
        )
        VALUES($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (article)
        DO UPDATE SET
            cabinet_id = EXCLUDED.cabinet_id,
            nomenclature_type_id = EXCLUDED.nomenclature_type_id,
            operation_id = EXCLUDED.operation_id,
            name = EXCLUDED.name,
            name_norm = EXCLUDED.name_norm,
            quantity_per_unit = EXCLUDED.quantity_per_unit,
            total_quantity = EXCLUDED.total_quantity
        """,
        cabinet_id,
        nomenclature_type_id,
        operation_id,
        article,
        name,
        name_norm,
        quantity_per_unit,
        total_quantity,
    )


async def import_csv(
    path: str,
    error_report_path: Optional[str],
    stats_out_path: Optional[str],
    strict: bool,
    incremental: bool,
) -> None:
    """Основная процедура импорта CSV."""  # основной сценарий
    db_url = _normalize_db_url(settings.database_url)  # приводим URL
    existing_articles: set = set()  # артикулы уже в БД

    project_cache: Dict[str, int] = {}  # кеш проектов
    cabinet_cache: Dict[tuple, int] = {}  # кеш шкафов
    stage_cache: Dict[int, int] = {}  # кеш этапов
    type_cache: Dict[tuple, int] = {}  # кеш видов (code, name)
    operation_cache: Dict[tuple, int] = {}  # кеш операций (nomenclature_type_id, code, name)

    processed = 0  # обработано строк
    skipped = 0  # пропущено строк
    missing_required = 0  # нет обязательных полей
    invalid_numeric = 0  # некорректные числовые значения
    duplicate_articles = 0  # конфликты артикулов

    seen_articles: Dict[str, Dict[str, Any]] = {}  # для конфликтов артикула
    error_rows: List[Dict[str, Any]] = []  # проблемные строки
    stats_projects: Dict[str, int] = {}  # статистика проектов
    stats_cabinets: Dict[str, int] = {}  # статистика шкафов
    stats_stages: Dict[int, int] = {}  # статистика этапов
    stats_types: Dict[tuple, int] = {}  # статистика видов
    stats_operations: Dict[tuple, int] = {}  # статистика операций

    def add_error(reason: str, raw_row: Dict[str, Any], row_number: int) -> None:
        """Сохраняет проблемную строку в отчёт."""  # собираем ошибки
        error_rows.append({"row_number": row_number, "reason": reason, **raw_row})  # пишем строку

    def safe_int(value: Optional[str], default: int = 0) -> Optional[int]:
        """Безопасное преобразование в int."""  # парсинг чисел
        if not value or not value.strip():
            return default if default else None
        try:
            return int(float(value))  # поддерживаем "1.0" -> 1
        except (ValueError, TypeError):
            return None

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
                        mapped[HEADER_ALIASES.get(key, key)] = v.strip() if v else ""

                    project_code = mapped.get("project")
                    cabinet_code = mapped.get("cabinet")
                    article = mapped.get("article")
                    name = mapped.get("name")
                    nom_type_code = safe_int(mapped.get("nomenclature_type_code"))
                    nom_type_name = mapped.get("nomenclature_type")
                    quantity_per_unit = safe_int(mapped.get("quantity_per_unit"), 1)
                    total_quantity = safe_int(mapped.get("total_quantity"), 1)
                    stage_code = safe_int(mapped.get("stage_code"))
                    # Наименование операции - это числовой код операции (~50 вариантов)
                    operation_code = safe_int(mapped.get("operation_name"))  # код операции из колонки "Наименование операции"
                    operation_name = f"Операция {operation_code}" if operation_code else ""  # генерируем название по коду
                    time_template = safe_int(mapped.get("time_template_minutes"), 0)

                    # Проверка обязательных полей
                    if not all([project_code, cabinet_code, article, name, 
                               nom_type_code is not None, nom_type_name,
                               stage_code is not None, operation_code is not None,
                               time_template is not None and time_template > 0]):
                        missing_required += 1
                        skipped += 1
                        add_error("missing_required_fields", mapped, row_number)
                        if strict:
                            raise RuntimeError(f"Строка {row_number}: отсутствуют обязательные поля")
                        continue

                    project_code = cast(str, project_code)
                    cabinet_code = cast(str, cabinet_code)
                    article = cast(str, article)
                    name = cast(str, name)
                    nom_type_code = cast(int, nom_type_code)
                    nom_type_name = cast(str, nom_type_name)
                    stage_code = cast(int, stage_code)
                    operation_code = cast(int, operation_code)
                    time_template = cast(int, time_template)

                    if incremental and article in existing_articles:  # уже в БД
                        skipped += 1
                        continue

                    name_norm = normalize_text(name)  # нормализация

                    # Проверка конфликтов артикула
                    prev = seen_articles.get(article)
                    if prev:
                        if (prev.get("name") != name or 
                            prev.get("nom_type_code") != nom_type_code or
                            prev.get("operation_code") != operation_code):
                            duplicate_articles += 1
                            add_error("duplicate_article_conflict", mapped, row_number)
                            if strict:
                                raise RuntimeError(f"Строка {row_number}: конфликт по артикулу {article}")
                    else:
                        seen_articles[article] = {
                            "name": name,
                            "nom_type_code": nom_type_code,
                            "operation_code": operation_code
                        }

                    # Создание/получение связанных сущностей
                    project_id = await _get_or_create_project(conn, project_code, project_cache)
                    cabinet_id = await _get_or_create_cabinet(conn, project_id, cabinet_code, cabinet_cache)
                    stage_id = await _get_or_create_stage(conn, stage_code, stage_cache)
                    type_id = await _get_or_create_nomenclature_type(
                        conn, nom_type_code, nom_type_name, stage_id, type_cache
                    )
                    operation_id = await _get_or_create_operation(
                        conn, type_id, operation_code, operation_name, time_template, operation_cache
                    )

                    await _upsert_item(
                        conn,
                        cabinet_id,
                        type_id,
                        operation_id,
                        article,
                        name,
                        name_norm,
                        quantity_per_unit or 1,
                        total_quantity or 1,
                    )

                    processed += 1
                    stats_projects[project_code] = stats_projects.get(project_code, 0) + 1
                    stats_cabinets[cabinet_code] = stats_cabinets.get(cabinet_code, 0) + 1
                    stats_stages[stage_code] = stats_stages.get(stage_code, 0) + 1
                    stats_types[(nom_type_code, nom_type_name)] = stats_types.get((nom_type_code, nom_type_name), 0) + 1
                    stats_operations[(operation_code, operation_name)] = stats_operations.get((operation_code, operation_name), 0) + 1
                    
                    if processed % 1000 == 0:
                        print(f"Импортировано строк: {processed}")

    print(f"Готово. Всего обработано строк: {processed}")
    if skipped > 0 or missing_required > 0 or invalid_numeric > 0 or duplicate_articles > 0:
        print(
            f"Проблемы: пропущено строк={skipped}, "
            f"отсутствуют обязательные поля={missing_required}, "
            f"некорректные числовые значения={invalid_numeric}, "
            f"дубликаты артикула={duplicate_articles}"
        )

    print("Статистика:")
    print(f"- проектов: {len(stats_projects)}")
    print(f"- шкафов: {len(stats_cabinets)}")
    print(f"- этапов: {len(stats_stages)}")
    print(f"- видов номенклатуры: {len(stats_types)}")
    print(f"- операций: {len(stats_operations)}")

    if error_report_path and error_rows:
        with open(error_report_path, "w", encoding="utf-8", newline="") as report:
            fieldnames = sorted({key for row in error_rows for key in row.keys()})
            writer = csv.DictWriter(report, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(error_rows)
        print(f"Отчёт об ошибках: {error_report_path}")

    if stats_out_path:
        stats_payload = {
            "processed": processed,
            "skipped": skipped,
            "missing_required": missing_required,
            "invalid_numeric": invalid_numeric,
            "duplicate_articles": duplicate_articles,
            "projects_count": len(stats_projects),
            "cabinets_count": len(stats_cabinets),
            "stages_count": len(stats_stages),
            "types_count": len(stats_types),
            "operations_count": len(stats_operations),
            "top_projects": sorted(stats_projects.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_cabinets": sorted(stats_cabinets.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_stages": sorted(stats_stages.items(), key=lambda x: x[1], reverse=True)[:10],
        }
        with open(stats_out_path, "w", encoding="utf-8") as stats_file:
            json.dump(stats_payload, stats_file, ensure_ascii=False, indent=2)
        print(f"Статистика: {stats_out_path}")


def parse_args() -> argparse.Namespace:
    """Читает параметры CLI."""  # аргументы командной строки
    parser = argparse.ArgumentParser(description="Импорт CSV в БД проекта")  # описание
    parser.add_argument("--path", required=True, help="Путь к CSV файлу")  # путь к CSV
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
            args.error_report,
            args.stats_out,
            args.strict,
            args.incremental,
        )
    )
