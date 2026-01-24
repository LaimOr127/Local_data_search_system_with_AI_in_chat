"""Pydantic-схемы запросов и ответов API."""  # описание входов/выходов

from typing import List, Optional, Dict, Any  # типы коллекций

from pydantic import BaseModel, Field  # базовые схемы
from typing import Literal  # фиксированные значения


class EstimateRequest(BaseModel):
    """Запрос на расчёт времени."""  # используется в /estimate
    names: List[str] = Field(min_length=1)  # список позиций
    format_report: bool = True  # нужен ли текстовый отчёт
    project_code: Optional[str] = None  # фильтр по проекту
    cabinet_code: Optional[str] = None  # фильтр по шкафу


class ChatMessage(BaseModel):
    """Сообщение в истории диалога."""  # один элемент истории
    role: str = Field(pattern="^(user|assistant|system)$")  # кто говорит
    content: str = Field(min_length=1)  # текст сообщения


class ChatRequest(BaseModel):
    """Запрос в интерактивный чат."""  # основной чат-эндпоинт
    message: str = Field(min_length=1)  # текст пользователя
    names: Optional[List[str]] = None  # позиции для поиска
    history: List[ChatMessage] = Field(default_factory=list)  # история диалога
    project_code: Optional[str] = None  # фильтр по проекту
    cabinet_code: Optional[str] = None  # фильтр по шкафу
    mode: Literal["auto", "chat", "estimate"] = "auto"  # режим работы
    use_llm: bool = True  # использовать Ollama для форматирования




class MatchedItem(BaseModel):
    """Одна найденная позиция."""  # результат поиска
    user_input: str  # исходная строка пользователя
    matched_name: str  # найденное наименование
    match_score: int  # оценка похожести
    article: str  # артикул
    cabinet: str  # шкаф
    project: str  # проект
    nomenclature_type_code: Optional[int] = None  # код вида номенклатуры
    nomenclature_type: str  # вид номенклатуры
    stage_code: Optional[int] = None  # код этапа
    stage: str  # этап
    operation_code: Optional[int] = None  # код операции
    operation_name: Optional[str] = None  # наименование операции
    quantity_per_unit: int = 1  # количество в 1 изделии
    total_quantity: int = 1  # итоговое количество
    time_per_unit: int  # время на позицию (уже умножено на total_quantity)


class EstimateResponse(BaseModel):
    """Ответ расчёта времени."""  # итоговый результат
    found_items: List[MatchedItem]  # найденные позиции
    not_found_items: List[str]  # не найденные
    total_time_by_cabinet: Dict[str, int]  # сумма по шкафам
    total_time_by_project: Dict[str, int]  # сумма по проектам
    report: Optional[str] = None  # текстовый отчёт
    warnings: List[str] = Field(default_factory=list)  # предупреждения
    raw_debug: Optional[Dict[str, Any]] = None  # диагностика


class ChatResponse(BaseModel):
    """Ответ чата: текст + данные расчёта."""  # комбинированный ответ
    reply: str  # ответ модели
    data: EstimateResponse  # результаты (если были)
