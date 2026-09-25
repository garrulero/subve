import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración central de la aplicación mediante Pydantic Settings.
    Lee automáticamente variables de entorno o archivo .env sin hardcoding.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Entorno
    APP_ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Entorno de ejecución de la aplicación",
    )

    # Base de Datos PostgreSQL / pgvector
    POSTGRES_USER: str = Field(
        default="subve_user",
        description="Usuario de conexión a PostgreSQL",
    )
    POSTGRES_PASSWORD: str = Field(
        default="subve_password",
        description="Contraseña de conexión a PostgreSQL",
    )
    POSTGRES_DB: str = Field(
        default="subvenciones_db",
        description="Nombre de la base de datos",
    )
    POSTGRES_HOST: str = Field(
        default="localhost",
        description="Host de PostgreSQL ('localhost' para desarrollo local, 'db' para Docker)",
    )
    POSTGRES_PORT: int = Field(
        default=5432,
        description="Puerto de PostgreSQL",
    )

    # URL Base para tracking y redirección de notificaciones
    BASE_URL_TRACKING: str = Field(
        default="http://localhost:8000/t",
        description="URL base para enlaces de seguimiento de clics",
    )

    # Configuración de IA (Vercel AI Gateway / OpenAI-compatible API)
    AI_GATEWAY_URL: str = Field(
        default="https://gateway.ai.vercel.com/v1",
        description="URL base de Vercel AI Gateway u otro proveedor OpenAI-compatible",
    )
    AI_API_KEY: str = Field(
        default="",
        description="API Key / Token para Vercel AI Gateway",
    )
    AI_MODEL: str = Field(
        default="jev",
        description="Nombre del modelo de IA a utilizar",
    )
    AI_TEMPERATURE: float = Field(
        default=0.0,
        description="Temperatura para generación determinista (0.0)",
    )
    AI_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Timeout de peticiones HTTP a la API de IA",
    )
    AI_MAX_RETRIES: int = Field(
        default=3,
        description="Número máximo de reintentos con exponential backoff",
    )

    # Gestión de rutas y ficheros relativos
    DATA_DIR: Path = Field(
        default=Path("./data"),
        description="Ruta para almacenamiento temporal o persistente de descargas",
    )
    LOGS_DIR: Path = Field(
        default=Path("./logs"),
        description="Ruta para logs de la aplicación",
    )

    @computed_field  # type: ignore[misc]
    @property
    def DATABASE_URL(self) -> str:
        """Genera la cadena de conexión compatible con SQLAlchemy y psycopg2."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def ensure_directories(self) -> None:
        """Crea los directorios de datos y logs si no existen en el sistema."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Instancia singleton en caché de las configuraciones de la aplicación."""
    _settings = Settings()
    _settings.ensure_directories()
    return _settings


settings: Settings = get_settings()
