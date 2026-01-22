"""HTTP-роуты API."""  # слой HTTP

from fastapi import APIRouter, Depends, HTTPException  # FastAPI
from sqlalchemy.ext.asyncio import AsyncSession  # сессии БД

from app.core.config import settings  # настройки
from app.db.session import get_session  # DI для БД
from app.models.schemas import EstimateRequest, EstimateResponse, MatchedItem, ChatRequest, ChatResponse  # схемы
from app.services.estimation import estimate  # поиск и расчет
from app.services.ollama import format_report, format_chat_reply, format_chat_only  # генерация текста

router = APIRouter(prefix="/v1")  # версия API


@router.post("/estimate", response_model=EstimateResponse)
async def estimate_endpoint(
    payload: EstimateRequest,
    session: AsyncSession = Depends(get_session),
) -> EstimateResponse:
    """Запускает поиск и расчет времени без чата."""  # чистый расчет
    if not payload.names:
        raise HTTPException(status_code=400, detail="Список наименований пуст")  # защита

    found_items, not_found, total_by_cabinet, total_by_project, debug = await estimate(  # основной расчет
        session,
        payload.names,
        payload.project_code,
        payload.cabinet_code,
    )

    report = None  # текстовый отчет
    warnings = []  # список предупреждений
    if payload.format_report:
        if not settings.enable_llm:
            warnings.append("LLM отключен настройками")  # LLM выключен
        else:
            try:
                report = await format_report(  # формируем отчет
                    {
                        "found_items": found_items,
                        "not_found_items": not_found,
                        "total_time_by_cabinet": total_by_cabinet,
                        "total_time_by_project": total_by_project,
                    }
                )
            except Exception:
                warnings.append("Не удалось получить ответ от Ollama")  # ошибка LLM

    return EstimateResponse(  # собираем ответ
        found_items=[MatchedItem(**item) for item in found_items],
        not_found_items=not_found,
        total_time_by_cabinet=total_by_cabinet,
        total_time_by_project=total_by_project,
        report=report,
        warnings=warnings,
        raw_debug=debug,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Интерактивный чат: с поиском или без, в зависимости от режима."""  # чат-эндпоинт
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Chat: mode={payload.mode}, names_count={len(payload.names) if payload.names else 0}")
    
    reply = ""  # текст ответа
    data: EstimateResponse  # данные расчета

    if payload.mode == "estimate" and not payload.names:
        data = EstimateResponse(
            found_items=[],
            not_found_items=[],
            total_time_by_cabinet={},
            total_time_by_project={},
            report=None,
            warnings=["Для режима estimate нужен список names. Отправьте позиции снова."],
            raw_debug=None,
        )
        reply = "Не получил список позиций. Отправьте корректный список и повторите запрос."
        return ChatResponse(reply=reply, data=data)

    if payload.mode == "estimate" or (payload.mode == "auto" and payload.names):  # режим поиска
        names = payload.names  # локальная переменная для type-checker
        if not names:
            data = EstimateResponse(
                found_items=[],
                not_found_items=[],
                total_time_by_cabinet={},
                total_time_by_project={},
                report=None,
                warnings=["Список names пуст. Отправьте позиции снова."],
                raw_debug=None,
            )
            reply = "Не получил список позиций. Отправьте корректный список и повторите запрос."
            return ChatResponse(reply=reply, data=data)
        try:
            found_items, not_found, total_by_cabinet, total_by_project, debug = await estimate(
                session,
                names,
                payload.project_code,
                payload.cabinet_code,
            )
            data = EstimateResponse(  # формируем структуру данных
                found_items=[MatchedItem(**item) for item in found_items],
                not_found_items=not_found,
                total_time_by_cabinet=total_by_cabinet,
                total_time_by_project=total_by_project,
                report=None,
                warnings=[],
                raw_debug=debug,
            )
        except Exception:
            data = EstimateResponse(
                found_items=[],
                not_found_items=[],
                total_time_by_cabinet={},
                total_time_by_project={},
                report=None,
                warnings=["Ошибка поиска или расчёта. Попробуйте отправить данные ещё раз."],
                raw_debug=None,
            )
            reply = "Произошла ошибка при расчёте. Проверьте входные данные и отправьте повторно."
            return ChatResponse(reply=reply, data=data)

        if settings.enable_llm:
            try:
                reply = await format_chat_reply(  # ответ с учетом расчетов
                    payload.message,
                    [msg.model_dump() for msg in payload.history],
                    data.model_dump(),
                )
            except Exception:
                reply = "Не удалось сформировать ответ от Ollama."  # ошибка LLM
        else:
            reply = "LLM отключен настройками."  # LLM выключен
    else:
        data = EstimateResponse(  # пустой расчет
            found_items=[],
            not_found_items=[],
            total_time_by_cabinet={},
            total_time_by_project={},
            report=None,
            warnings=["Поиск не выполнялся, список наименований не передан."],
            raw_debug=None,
        )
        if settings.enable_llm:
            try:
                reply = await format_chat_only(  # просто чат
                    payload.message,
                    [msg.model_dump() for msg in payload.history],
                )
            except Exception:
                reply = "Не удалось сформировать ответ от Ollama."  # ошибка LLM
        else:
            reply = "LLM отключен настройками."  # LLM выключен

    return ChatResponse(reply=reply, data=data)  # итоговый ответ
