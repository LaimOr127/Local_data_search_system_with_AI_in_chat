"""Точка входа FastAPI приложения."""  # модуль запуска сервиса

from fastapi import FastAPI  # основной класс приложения
from fastapi.responses import FileResponse  # отдача HTML
from fastapi.staticfiles import StaticFiles  # статика

from app.api.routes import router  # роуты API
from app.core.config import settings  # конфигурация из .env
from app.core.logging import setup_logging  # настройка логирования


def create_app() -> FastAPI:
    """Создаёт и настраивает приложение FastAPI."""  # единая фабрика приложения
    setup_logging()  # включаем логирование
    app = FastAPI(title=settings.app_name)  # создаём приложение
    app.include_router(router)  # подключаем роуты
    app.mount("/static", StaticFiles(directory="web"), name="static")  # статика UI

    @app.get("/")  # лендинг / интерфейс
    async def index() -> FileResponse:
        return FileResponse("web/index.html")  # главная страница

    return app  # возвращаем готовый инстанс


app = create_app()  # объект приложения для ASGI
