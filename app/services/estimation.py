"""Сервис расчёта времени по найденным позициям."""  # основной алгоритм

from collections import defaultdict  # словари с дефолтами
from typing import Dict, List, Tuple, Optional  # типы

from sqlalchemy.ext.asyncio import AsyncSession  # асинхронные сессии БД

from app.core.config import settings  # настройки поиска
from app.repositories import items as items_repo  # запросы к БД
from app.services.matching import pick_best_matches  # fuzzy-ранжирование
from app.utils.normalization import normalize_text  # нормализация строк


def _row_to_match(user_input: str, row: Dict, score: int) -> Dict:
    """Преобразует строку из БД в формат ответа."""  # адаптер данных
    return {  # приводим к единому виду
        "user_input": user_input,  # исходная строка
        "matched_name": row.get("name"),  # найденное имя
        "match_score": score,  # оценка похожести
        "article": row.get("article"),  # артикул
        "cabinet": row.get("cabinet_code"),  # шкаф
        "project": row.get("project_code"),  # проект
        "nomenclature_type": row.get("type_name"),  # вид номенклатуры
        "stage": row.get("stage_name"),  # этап
        "time_per_unit": row.get("assembly_time_minutes"),  # время по позиции
    }


async def estimate(
    session: AsyncSession,
    names: List[str],
    project_code: Optional[str],
    cabinet_code: Optional[str],
) -> Tuple[List[Dict], List[str], Dict[str, int], Dict[str, int], Dict]:
    """Основной алгоритм: поиск, сопоставление, суммирование."""  # ядро логики
    normalized = [normalize_text(name) for name in names]  # нормализация входа

    exact_rows = await items_repo.fetch_exact_matches(  # точный поиск
        session,
        normalized,
        project_code,
        cabinet_code,
    )
    exact_by_norm: Dict[str, List[Dict]] = defaultdict(list)  # группируем по норме
    for row in exact_rows:
        exact_by_norm[row["name_norm"]].append(row)  # складываем в группу

    found_items: List[Dict] = []  # найденные позиции
    not_found: List[str] = []  # список ненайденных
    debug: Dict[str, List[Dict]] = {"matches": []}  # диагностика
    seen_articles_per_input: Dict[str, set] = {}  # отслеживаем артикулы для каждого входного запроса
    global_seen_articles: set = set()  # глобальная дедупликация: один артикул = одна позиция

    for user_input, norm in zip(names, normalized):
        seen_articles = seen_articles_per_input.setdefault(user_input, set())  # артикулы для этого запроса
        
        exact = exact_by_norm.get(norm)  # проверяем точные совпадения
        if exact:
            debug["matches"].append({"input": user_input, "exact": len(exact), "fuzzy": 0})  # лог
            # Для точных совпадений выбираем первый (лучший) вариант, если артикул еще не использован
            for row in exact:
                article = row.get("article")  # артикул позиции
                if article and article not in global_seen_articles:  # глобальная проверка
                    global_seen_articles.add(article)  # отмечаем глобально
                    seen_articles.add(article)  # отмечаем для этого запроса
                    found_items.append(_row_to_match(user_input, row, 100))  # 100% совпадение
                    break  # берем только первый, если артикул еще не использован
            continue  # дальше не ищем

        tokens = [token for token in norm.split(" ") if token]  # токены для fallback
        if settings.use_pg_trgm:
            candidates = await items_repo.fetch_candidates_pg_trgm(
                session,
                norm,
                settings.max_candidates,
                project_code,
                cabinet_code,
            )
        else:
            candidates = await items_repo.fetch_candidates_token(
                session,
                tokens,
                settings.max_candidates,
                project_code,
                cabinet_code,
            )

        best = pick_best_matches(  # фильтруем по порогу
            norm,
            candidates,
            settings.max_results_per_input,
        )
        if not best:
            debug["matches"].append({"input": user_input, "exact": 0, "fuzzy": 0})  # лог
            not_found.append(user_input)  # не нашли
            continue  # идём дальше

        debug["matches"].append({"input": user_input, "exact": 0, "fuzzy": len(best)})  # лог
        # Для fuzzy совпадений берем только первый (лучший) вариант, если артикул еще не использован
        for row in best:
            article = row.get("article")  # артикул позиции
            if article and article not in global_seen_articles:  # глобальная проверка
                global_seen_articles.add(article)  # отмечаем глобально
                seen_articles.add(article)  # отмечаем для этого запроса
                score = row.pop("match_score")  # забираем оценку
                found_items.append(_row_to_match(user_input, row, score))  # добавляем в ответ
                break  # берем только первый, если артикул еще не использован

    total_by_cabinet: Dict[str, int] = defaultdict(int)  # сумма по шкафам
    total_by_project: Dict[str, int] = defaultdict(int)  # сумма по проектам

    for item in found_items:
        total_by_cabinet[item["cabinet"]] += int(item["time_per_unit"])  # добавляем время
        total_by_project[item["project"]] += int(item["time_per_unit"])  # добавляем время

    return found_items, not_found, dict(total_by_cabinet), dict(total_by_project), debug  # итог
