"""Инициализация подключения к БД и сессии SQLAlchemy."""  # база данных

from typing import AsyncGenerator  # тип для yield

from sqlalchemy.ext.asyncio import (  # async SQLAlchemy
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings  # настройки приложения


engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)  # движок БД
AsyncSessionLocal = async_sessionmaker(  # фабрика async-сессий
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Возвращает асинхронную сессию БД для DI в FastAPI."""  # зависимость FastAPI
    async with AsyncSessionLocal() as session:  # контекст сессии
        yield session  # отдаём наружу
