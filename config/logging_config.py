import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

from config.settings import settings


def setup_logging() -> None:
    """
    Configura el sistema centralizado de logging persistente y rotativo en disco.
    Crea manejadores segregados para el flujo general (app.log), errores globales (errors.log),
    fallos específicos del clasificador IA (classifier_errors.log) y actividad de scrapers (scrapers.log).
    """
    settings.ensure_directories()
    logs_dir: Path = settings.LOGS_DIR

    # Formato estándar estructurado con marca temporal, nivel, módulo, archivo, línea y mensaje
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d]: %(message)s"
    )

    # 1. Handlers Globales (Root Logger)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.APP_ENV == "development" else logging.INFO)

    # Limpiar manejadores previos para evitar salidas duplicadas
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Consola / STDOUT (para Docker y desarrollo en vivo)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if settings.APP_ENV == "development" else logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # app.log (Flujo completo del sistema a nivel INFO+)
    app_handler = RotatingFileHandler(
        logs_dir / "app.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)

    # errors.log (Filtra EXCLUSIVAMENTE eventos ERROR y CRITICAL de toda la app)
    errors_handler = RotatingFileHandler(
        logs_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)
    root_logger.addHandler(errors_handler)

    # 2. Handler Segregado: ai.classifier (classifier_errors.log)
    classifier_logger = logging.getLogger("ai.classifier")
    classifier_errors_handler = RotatingFileHandler(
        logs_dir / "classifier_errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    classifier_errors_handler.setLevel(logging.ERROR)
    classifier_errors_handler.setFormatter(formatter)
    classifier_logger.addHandler(classifier_errors_handler)

    # 3. Handler Segregado: scrapers (scrapers.log)
    scrapers_logger = logging.getLogger("scrapers")
    scrapers_handler = RotatingFileHandler(
        logs_dir / "scrapers.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    scrapers_handler.setLevel(logging.INFO)
    scrapers_handler.setFormatter(formatter)
    scrapers_logger.addHandler(scrapers_handler)
