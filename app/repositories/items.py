"""SQL-запросы для выборки позиций из БД."""  # слой доступа к данным

from typing import Iterable, List, Dict, Any, Optional, Tuple  # типы

from sqlalchemy import text, bindparam  # SQL-утилиты
from sqlalchemy.ext.asyncio import AsyncSession  # асинхронная сессия


# Базовый SELECT с нужными JOIN для расчетов.
BASE_SELECT = """  # общий селект для всех выборок
SELECT
    i.id,
    i.name,
    COALESCE(i.name_norm, LOWER(i.name)) AS name_norm,
    i.article,
    c.cabinet_code,
    p.project_code,
    nt.type_name,
    s.stage_name,
    i.assembly_time_minutes
FROM items i
JOIN cabinets c ON c.id = i.cabinet_id
JOIN projects p ON p.id = c.project_id
JOIN nomenclature_types nt ON nt.id = i.nomenclature_type_id
JOIN stages s ON s.id = nt.stage_id
"""


def _build_filters(project_code: Optional[str], cabinet_code: Optional[str]) -> Tuple[str, dict]:
    """Строит SQL-фильтры по проекту и шкафу."""  # локальная сборка фильтров
    clauses = []  # условия WHERE
    params: dict = {}  # параметры для биндинга
    if project_code:
        clauses.append("p.project_code = :project_code")  # фильтр по проекту
        params["project_code"] = project_code  # значение проекта
    if cabinet_code:
        clauses.append("c.cabinet_code = :cabinet_code")  # фильтр по шкафу
        params["cabinet_code"] = cabinet_code  # значение шкафа
    if not clauses:
        return "", params  # нет фильтров
    return " AND " + " AND ".join(clauses), params  # склеиваем условия


async def fetch_exact_matches(
    session: AsyncSession,
    names_norm: Iterable[str],
    project_code: Optional[str],
    cabinet_code: Optional[str],
) -> List[Dict[str, Any]]:
    """Возвращает точные совпадения по нормализованному имени."""  # точный поиск
    filter_sql, filter_params = _build_filters(project_code, cabinet_code)  # фильтры
    query = text(  # формируем SQL
        BASE_SELECT
        + " WHERE COALESCE(i.name_norm, LOWER(i.name)) IN :names"
        + filter_sql
    ).bindparams(bindparam("names", expanding=True))

    params = {"names": list(names_norm)}  # параметры имен
    params.update(filter_params)  # добавляем фильтры
    result = await session.execute(query, params)  # выполняем запрос
    return [dict(row._mapping) for row in result.fetchall()]  # отдаём список


async def fetch_candidates_pg_trgm(
    session: AsyncSession,
    name_norm: str,
    limit: int,
    project_code: Optional[str],
    cabinet_code: Optional[str],
) -> List[Dict[str, Any]]:
    """Возвращает кандидатов по pg_trgm similarity."""  # быстрые кандидаты
    filter_sql, filter_params = _build_filters(project_code, cabinet_code)  # фильтры
    query = text(  # формируем SQL
        BASE_SELECT
        + " WHERE COALESCE(i.name_norm, LOWER(i.name)) % :name_norm"
        + filter_sql
        + " ORDER BY similarity(COALESCE(i.name_norm, LOWER(i.name)), :name_norm) DESC"
        + " LIMIT :limit"
    )
    params = {"name_norm": name_norm, "limit": limit}  # параметры поиска
    params.update(filter_params)  # добавляем фильтры
    result = await session.execute(query, params)  # выполняем запрос
    return [dict(row._mapping) for row in result.fetchall()]  # отдаём список


async def fetch_candidates_token(
    session: AsyncSession,
    tokens: Iterable[str],
    limit: int,
    project_code: Optional[str],
    cabinet_code: Optional[str],
) -> List[Dict[str, Any]]:
    """Возвращает кандидатов по токенам (ILIKE)."""  # fallback без pg_trgm
    patterns = [f"%{token}%" for token in tokens if token]  # токены как маски
    if not patterns:
        return []  # нечего искать

    filter_sql, filter_params = _build_filters(project_code, cabinet_code)  # фильтры
    query = text(  # формируем SQL
        BASE_SELECT
        + " WHERE COALESCE(i.name_norm, LOWER(i.name)) ILIKE ANY(:patterns)"
        + filter_sql
        + " LIMIT :limit"
    )
    params = {"patterns": patterns, "limit": limit}  # параметры поиска
    params.update(filter_params)  # добавляем фильтры
    result = await session.execute(query, params)  # выполняем запрос
    return [dict(row._mapping) for row in result.fetchall()]  # отдаём список
