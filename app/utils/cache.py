"""Простое кэширование результатов поиска в памяти."""  # для ускорения повторных запросов

from functools import lru_cache
from typing import Tuple, List, Optional


@lru_cache(maxsize=1000)  # кэш до 1000 запросов
def get_cache_key(
    names_tuple: Tuple[str, ...],
    project_code: Optional[str],
    cabinet_code: Optional[str],
) -> str:
    """Генерирует ключ кэша на основе входных данных."""  # уникальный ключ
    parts = ["|".join(names_tuple)]  # список имён
    if project_code:
        parts.append(f"p:{project_code}")  # проект
    if cabinet_code:
        parts.append(f"c:{cabinet_code}")  # шкаф
    return "||".join(parts)  # итоговый ключ
