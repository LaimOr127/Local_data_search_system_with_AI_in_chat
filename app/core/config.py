"""Конфигурация приложения из переменных окружения."""  # единая точка настроек

from pydantic_settings import BaseSettings, SettingsConfigDict  # настройки через pydantic


class Settings(BaseSettings):
    """Набор параметров приложения."""  # читаются из .env
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # игнорируем лишнее

    app_name: str = "assembly-estimator"  # название сервиса
    api_host: str = "127.0.0.1"  # адрес прослушивания
    api_port: int = 8000  # порт API

    database_url: str  # строка подключения к PostgreSQL
    use_pg_trgm: bool = True  # использовать pg_trgm для поиска

    fuzzy_min_score: int = 70  # порог похожести (снижен для более гибкого поиска)
    max_candidates: int = 30  # кандидатов из БД (уменьшено для скорости)
    max_results_per_input: int = 1  # итоговых совпадений (только лучший матч)

    ollama_base_url: str = "http://localhost:11434"  # локальный Ollama
    ollama_model: str = "qwen2.5:3b"  # модель для генерации текста
    enable_llm: bool = True  # общий флаг LLM


settings = Settings()  # глобальный объект настроек
