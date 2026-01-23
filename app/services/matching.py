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
    query_tokens = set(query_norm.split())  # токены запроса для проверки покрытия
    
    for candidate in candidates:
        name_norm = candidate.get("name_norm") or ""  # нормализованное имя
        name_tokens = set(name_norm.split())  # токены кандидата
        
        # Используем несколько метрик и берём максимальную для более точного поиска
        ratio_score = fuzz.ratio(query_norm, name_norm)  # точное сравнение
        partial_score = fuzz.partial_ratio(query_norm, name_norm)  # частичное совпадение
        token_sort_score = fuzz.token_sort_ratio(query_norm, name_norm)  # по токенам (порядок не важен)
        token_set_score = fuzz.token_set_ratio(query_norm, name_norm)  # по множеству токенов
        wr_score = fuzz.WRatio(query_norm, name_norm)  # взвешенное соотношение
        
        # Бонус за покрытие всех токенов запроса (для более точных совпадений)
        coverage_bonus = 0
        if query_tokens and name_tokens:
            coverage = len(query_tokens & name_tokens) / len(query_tokens)  # доля покрытых токенов
            if coverage >= 0.8:  # если покрыто 80%+ токенов
                coverage_bonus = int(coverage * 10)  # бонус до 10 баллов
        
        # Берём максимальную оценку из всех метрик + бонус за покрытие
        base_score = int(max(ratio_score, partial_score, token_sort_score, token_set_score, wr_score))
        score = min(100, base_score + coverage_bonus)  # ограничиваем максимум 100
        
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
