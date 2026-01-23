"""Интеграция с локальной Ollama для генерации текста."""  # генерация ответов

from typing import Dict, Any  # типы

import httpx  # HTTP-клиент

from app.core.config import settings  # настройки модели


SYSTEM_PROMPT = (  # системный промпт для отчёта
    "Ты — помощник-аналитик. Ты получаешь структурированные данные о найденных "
    "позициях оборудования и расчете времени сборки. Твоя задача — составить ясный, "
    "дружелюбный отчет для пользователя.\n\n"
    "Обязательные элементы отчета:\n"
    "1. Краткая сводка: сколько позиций найдено, общее ориентировочное время.\n"
    "2. Детали по проектам/шкафам (маркированным списком).\n"
    "3. Предупреждение о ненайденных позициях (если есть).\n"
    "4. Указание предположений (если применялось нечеткое сопоставление).\n\n"
    "Используй только предоставленные данные. Будь лаконичен."
)

CHAT_SYSTEM_PROMPT = (  # системный промпт для чата
    "Ты — ассистент для интерактивного чата по расчету времени сборки. "
    "Отвечай кратко и по делу. Используй данные расчёта. "
    "Сформируй итог: общая оценка времени, разбиение по шкафам, "
    "и отметь ненайденные позиции (если есть)."
)


async def format_report(payload: Dict[str, Any]) -> str:
    """Формирует итоговый отчет по результатам расчета."""  # отчётный режим
    if not settings.enable_llm:
        return ""  # LLM отключен

    user_prompt = f"Вот данные: {payload}. Составь отчет."  # текст запроса

    request_data = {  # тело запроса к Ollama
        "model": settings.ollama_model,
        "system": SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # клиент HTTP с увеличенным таймаутом
            response = await client.post(  # отправка запроса
                f"{settings.ollama_base_url}/api/generate",
                json=request_data,
            )
            response.raise_for_status()  # ошибка при не-2xx
            data = response.json()  # ответ модели
            result = data.get("response", "").strip()  # готовый текст
            if not result:
                raise ValueError("Ollama вернул пустой ответ")  # проверка на пустой ответ
            return result  # возвращаем результат
    except httpx.TimeoutException:
        raise Exception(f"Ollama timeout: не ответила за 120 секунд")  # таймаут
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")  # HTTP ошибка
    except Exception as e:
        raise Exception(f"Ollama error: {str(e)}")  # прочие ошибки


async def format_chat_reply(
    message: str,
    history: list[dict],
    payload: Dict[str, Any],
) -> str:
    """Формирует ответ чата с учётом результатов поиска."""  # чат + данные
    if not settings.enable_llm:
        return ""  # LLM отключен

    by_cabinet = payload.get("total_time_by_cabinet", {})
    by_project = payload.get("total_time_by_project", {})
    total_time = sum(by_cabinet.values())  # общее время (сумма по шкафам)
    
    summary = {
        "found_count": len(payload.get("found_items", [])),
        "not_found": payload.get("not_found_items", []),
        "total_time_minutes": total_time,
        "total_by_cabinet": by_cabinet,
        "total_by_project": by_project,
    }
    user_prompt = (  # промпт с историей и данными
        f"Сообщение пользователя: {message}. "
        f"Результаты расчёта: {summary}. "
        "Сформируй понятный ответ. ОБЯЗАТЕЛЬНО укажи общее время (total_time_minutes) в начале, "
        "затем разбивку по шкафам и проектам."
    )

    request_data = {  # тело запроса к Ollama
        "model": settings.ollama_model,
        "system": CHAT_SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # клиент HTTP с увеличенным таймаутом
            response = await client.post(  # отправка запроса
                f"{settings.ollama_base_url}/api/generate",
                json=request_data,
            )
            response.raise_for_status()  # ошибка при не-2xx
            data = response.json()  # ответ модели
            result = data.get("response", "").strip()  # готовый текст
            if not result:
                raise ValueError("Ollama вернул пустой ответ")  # проверка на пустой ответ
            return result  # возвращаем результат
    except httpx.TimeoutException:
        raise Exception(f"Ollama timeout: не ответила за 120 секунд")  # таймаут
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")  # HTTP ошибка
    except Exception as e:
        raise Exception(f"Ollama error: {str(e)}")  # прочие ошибки


async def format_chat_only(message: str, history: list[dict]) -> str:
    """Формирует ответ чата без запуска поиска."""  # чистый чат
    if not settings.enable_llm:
        return ""  # LLM отключен

    user_prompt = (  # промпт без данных поиска
        f"Сообщение пользователя: {message}. "
        f"История: {history}. "
        "Ответь как ассистент. Поиск и расчёты не выполняй."
    )

    request_data = {  # тело запроса к Ollama
        "model": settings.ollama_model,
        "system": CHAT_SYSTEM_PROMPT,
        "prompt": user_prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # клиент HTTP с увеличенным таймаутом
            response = await client.post(  # отправка запроса
                f"{settings.ollama_base_url}/api/generate",
                json=request_data,
            )
            response.raise_for_status()  # ошибка при не-2xx
            data = response.json()  # ответ модели
            result = data.get("response", "").strip()  # готовый текст
            if not result:
                raise ValueError("Ollama вернул пустой ответ")  # проверка на пустой ответ
            return result  # возвращаем результат
    except httpx.TimeoutException:
        raise Exception(f"Ollama timeout: не ответила за 120 секунд")  # таймаут
    except httpx.HTTPStatusError as e:
        raise Exception(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")  # HTTP ошибка
    except Exception as e:
        raise Exception(f"Ollama error: {str(e)}")  # прочие ошибки
