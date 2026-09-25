from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import settings

# Creación de motor SQLAlchemy con pooling robusto para producción
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=(settings.APP_ENV == "development"),
)

# Fábrica de sesiones para transacciones
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos del proyecto."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Generador de sesión de base de datos para dependencias FastAPI o scripts.
    Garantiza el cierre automático de la conexión al finalizar el scope.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """
    Inicializa extensiones de PostgreSQL (pgvector), aplica migraciones de esquema
    y crea todas las tablas registradas en los metadatos de SQLAlchemy.
    """
    # Importar modelos aquí para asegurar que están registrados en Base.metadata
    from db import models  # noqa: F401

    with engine.connect() as conn:
        # Activar extensión pgvector si está disponible en la imagen Postgres
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
        except Exception:
            # En caso de entornos sin pgvector preinstalado a nivel de superusuario
            pass

        # Aplicar migraciones de columnas Fase 2 si el dialecto es PostgreSQL
        try:
            dialect_name = conn.dialect.name
            if dialect_name == "postgresql":
                fase2_statements = [
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS resumen_ejecutivo TEXT;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS presupuesto_total DOUBLE PRECISION;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS cuantia_maxima_solicitud DOUBLE PRECISION;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS tipo_ayuda VARCHAR(50);",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS beneficiarios_detalle TEXT;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS requisitos_principales JSONB;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS gastos_subvencionables JSONB;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS tags JSONB;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS score_relevancia DOUBLE PRECISION;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS score_justificacion TEXT;",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS plazo_solicitud_texto VARCHAR(255);",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);",
                    "ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS ai_processed_at TIMESTAMP WITH TIME ZONE;",
                ]
                for stmt in fase2_statements:
                    conn.execute(text(stmt))
                conn.commit()
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)

