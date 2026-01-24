"""Функции ранжирования для нечеткого сопоставления с поддержкой синонимов."""  # логика fuzzy

from typing import Dict, List, Tuple  # типы

from rapidfuzz import fuzz  # type: ignore  # метрики похожести

from app.core.config import settings  # настройки порогов


# Базовый словарь синонимов для улучшения поиска
# Формат: ключ - основное слово, значение - список синонимов
SYNONYMS_DICT = {
    # Примеры - можно расширить
    "кот": ["котенок", "котик", "котёнок"],
    "шкаф": ["шкафчик", "шкафу"],
    "щит": ["щиток", "щитовая"],
    "управление": ["управляющий", "управляющая"],
    "насос": ["насосный", "насосная"],
}


def _expand_query_with_synonyms(query_norm: str) -> List[str]:
    """Расширяет запрос синонимами для улучшения поиска."""  # поиск синонимов
    queries = [query_norm]  # исходный запрос
    query_tokens = query_norm.split()  # токены запроса
    
    # Проверяем каждый токен на наличие синонимов
    for token in query_tokens:
        if token in SYNONYMS_DICT:
            for synonym in SYNONYMS_DICT[token]:
                # Создаем варианты запроса с заменой токена на синоним
                expanded = query_norm.replace(token, synonym)
                if expanded not in queries:
                    queries.append(expanded)
    
    return queries  # возвращаем все варианты


def _calculate_similarity_score(query_norm: str, name_norm: str) -> int:
    """Вычисляет оценку похожести с использованием нескольких метрик."""  # комплексная оценка
    query_tokens = set(query_norm.split())  # токены запроса
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
    
    # Бонус за начало слова (например, "кот" в "котенок")
    prefix_bonus = 0
    if query_tokens and name_tokens:
        for q_token in query_tokens:
            for n_token in name_tokens:
                if len(q_token) >= 3 and n_token.startswith(q_token):
                    prefix_bonus += 5  # бонус за префикс
                elif len(n_token) >= 3 and q_token.startswith(n_token):
                    prefix_bonus += 5  # обратный префикс
    
    # Берём максимальную оценку из всех метрик + бонусы
    base_score = int(max(ratio_score, partial_score, token_sort_score, token_set_score, wr_score))
    score = min(100, base_score + coverage_bonus + min(prefix_bonus, 10))  # ограничиваем максимум 100
    
    return score


def rank_candidates(
    query_norm: str,
    candidates: List[Dict],
) -> List[Tuple[int, Dict]]:
    """Оценивает кандидатов и сортирует по убыванию оценки."""  # основной скоринг
    scored = []  # список (оценка, объект)
    expanded_queries = _expand_query_with_synonyms(query_norm)  # варианты запроса с синонимами
    
    for candidate in candidates:
        name_norm = candidate.get("name_norm") or ""  # нормализованное имя
        
        # Оцениваем по всем вариантам запроса (включая синонимы) и берём максимальную оценку
        max_score = 0
        for expanded_query in expanded_queries:
            score = _calculate_similarity_score(expanded_query, name_norm)
            max_score = max(max_score, score)
        
        scored.append((max_score, candidate))  # сохраняем максимальную оценку
    
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
