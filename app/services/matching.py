"""Функции ранжирования для нечеткого сопоставления."""  # логика fuzzy

from typing import Dict, List, Tuple  # типы

from rapidfuzz import fuzz  # type: ignore  # метрики похожести

from app.core.config import settings  # настройки порогов


def rank_candidates(
    query_norm: str,
    candidates: List[Dict],
) -> List[Tuple[int, Dict]]:
    """Оценивает кандидатов и сортирует по убыванию оценки."""  # основной скоринг
    scored = []  # список (оценка, объект)
    for candidate in candidates:
        name_norm = candidate.get("name_norm") or ""  # нормализованное имя
        
        # Используем несколько метрик и берём максимальную для более точного поиска
        ratio_score = fuzz.ratio(query_norm, name_norm)  # точное сравнение
        partial_score = fuzz.partial_ratio(query_norm, name_norm)  # частичное совпадение
        token_sort_score = fuzz.token_sort_ratio(query_norm, name_norm)  # по токенам (порядок не важен)
        token_set_score = fuzz.token_set_ratio(query_norm, name_norm)  # по множеству токенов
        wr_score = fuzz.WRatio(query_norm, name_norm)  # взвешенное соотношение
        
        # Берём максимальную оценку из всех метрик для более гибкого поиска
        score = int(max(ratio_score, partial_score, token_sort_score, token_set_score, wr_score))
        
        scored.append((score, candidate))  # сохраняем оценку
    scored.sort(key=lambda x: x[0], reverse=True)  # сортируем по убыванию
    return scored  # возвращаем ранжирование


def pick_best_matches(
    query_norm: str,
    candidates: List[Dict],
    max_results: int,
) -> List[Dict]:
    """Возвращает топ совпадений выше порога."""  # фильтрация по порогу
    ranked = rank_candidates(query_norm, candidates)  # сортируем кандидатов
    results = []  # итоговый список
    for score, candidate in ranked:
        if score < settings.fuzzy_min_score:
            break  # дальше слишком низко
        candidate_copy = dict(candidate)  # копия, чтобы не портить исходное
        candidate_copy["match_score"] = score  # добавляем оценку
        results.append(candidate_copy)  # сохраняем
        if len(results) >= max_results:
            break  # ограничение по количеству
    return results  # отдаём совпадения
