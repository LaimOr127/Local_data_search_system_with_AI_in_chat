"""Нормализация текстовых строк для поиска."""  # утилита для строк

import re  # регулярные выражения


def normalize_text(text: str) -> str:
    """Приводит строку к базовому нормализованному виду."""  # упрощение строки
    text = text.strip().lower()  # обрезаем и приводим к нижнему регистру
    text = text.replace("ё", "е")  # убираем варианты "ё"
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)  # чистим знаки
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE)  # сжимаем пробелы
    return text.strip()  # итог без крайних пробелов
