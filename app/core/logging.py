"""Базовая настройка логирования."""  # минимальные настройки логов

import logging  # стандартный модуль логирования


def setup_logging() -> None:
    """Включает единый формат логов."""  # единый стиль на всё приложение
    logging.basicConfig(  # базовая конфигурация
        level=logging.INFO,  # уровень INFO
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",  # шаблон строки
    )
