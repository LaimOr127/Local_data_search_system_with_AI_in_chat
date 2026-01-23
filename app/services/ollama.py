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
    "Ты — ассистент для интерактивного чата по расчету времени сборки оборудования. "
    "Твоя задача — сформировать понятный и структурированный ответ на русском языке. "
    "Всегда начинай с общего времени, затем разбивку по шкафам и проектам. "
    "Используй данные из результатов расчёта. Будь конкретным и информативным."
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
    not_found_items = payload.get("not_found_items", [])
    
    summary = {
        "found_count": len(payload.get("found_items", [])),
        "not_found": not_found_items,
        "total_time_minutes": total_time,
        "total_by_cabinet": by_cabinet,
        "total_by_project": by_project,
    }
    # Форматируем данные для более понятного промпта
    cabinet_lines = "\n".join([f"- Шкаф \"{k}\": {v} минут" for k, v in by_cabinet.items()])
    project_lines = "\n".join([f"- Проект \"{k}\": {v} минут" for k, v in by_project.items()])
    not_found_text = ", ".join(not_found_items) if not_found_items else "нет"
    
    user_prompt = (  # промпт с историей и данными
        f"Пользователь написал: {message}\n\n"
        f"Результаты расчёта времени сборки:\n"
        f"Найдено позиций: {summary['found_count']}\n"
        f"Общее время: {total_time} минут (~{total_time // 60} часов {total_time % 60} минут)\n\n"
        f"Время по шкафам:\n{cabinet_lines}\n\n"
        f"Время по проектам:\n{project_lines}\n\n"
        f"Ненайденные позиции: {not_found_text}\n\n"
        "Сформируй понятный ответ на русском языке. Начни с общего времени, затем разбивку по шкафам и проектам."
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

    # Форматируем историю для более понятного промпта
    history_text = ""
    if history:
        history_lines = []
        for msg in history[-5:]:  # последние 5 сообщений
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role == 'user':
                history_lines.append(f"Пользователь: {content}")
            elif role == 'assistant':
                history_lines.append(f"Ассистент: {content}")
        history_text = "\n".join(history_lines)
    
    history_part = ""
    if history_text:
        history_part = f"История разговора:\n{history_text}\n\n"
    
    user_prompt = (  # промпт без данных поиска
        f"Пользователь написал: {message}\n\n"
        f"{history_part}"
        "Ответь как ассистент по расчету времени сборки оборудования. "
        "Будь кратким и полезным. Если пользователь спрашивает о расчете, напомни, что нужно отправить список позиций."
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
