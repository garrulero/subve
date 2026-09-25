import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import Convocatoria

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Clase abstracta base para la orquestación e ingesta de boletines oficiales.
    Define el ciclo de vida: extracción -> filtrado -> enriquecimiento -> persistencia idempotente.
    """

    def __init__(self, name: str, source_id: str) -> None:
        self.name: str = name
        self.source_id: str = source_id

    @abstractmethod
    def fetch_items(self) -> List[Dict[str, Any]]:
        """
        Descarga y parsea la fuente de datos (XML/RSS/API/HTML).
        Retorna una lista de diccionarios con la información cruda de cada anuncio.
        """
        pass

    @abstractmethod
    def filter_relevant(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Aplica reglas de negocio o filtrado por palabras clave para descartar
        anuncios irrelevantes (nombramientos internos, licencias de obra menores, etc.)
        antes de procesar el texto completo.
        """
        pass

    @abstractmethod
    def enrich_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Descarga el detalle completo del anuncio si es necesario (texto_crudo,
        organismo emisor, fecha de publicación) y normaliza los campos.
        """
        pass

    def save_records(self, db: Session, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Inserta de forma masiva e idempotente los registros en la base de datos.
        Aplica la estrategia ON CONFLICT (id_origen) DO NOTHING para evitar duplicados.
        """
        if not records:
            return {"total": 0, "inserted": 0, "skipped": 0}

        inserted_count = 0
        skipped_count = 0

        # Manejo compatible con PostgreSQL pg_insert
        try:
            dialect_name = db.bind.dialect.name if db.bind else "postgresql"
        except Exception:
            dialect_name = "postgresql"

        if dialect_name == "postgresql":
            for record in records:
                try:
                    stmt = (
                        pg_insert(Convocatoria)
                        .values(**record)
                        .on_conflict_do_nothing(index_elements=["id_origen"])
                    )
                    result = db.execute(stmt)
                    db.commit()
                    if result.rowcount > 0:
                        inserted_count += 1
                    else:
                        skipped_count += 1
                except Exception as ex:
                    db.rollback()
                    logger.error(
                        f"[{self.name}] Error insertando registro {record.get('id_origen')}: {ex}",
                        exc_info=True,
                    )
        else:
            # Fallback para pruebas o dialectos que no soportan pg_insert
            for record in records:
                exists = (
                    db.query(Convocatoria)
                    .filter(Convocatoria.id_origen == record["id_origen"])
                    .first()
                )
                if not exists:
                    convocatoria = Convocatoria(**record)
                    db.add(convocatoria)
                    db.commit()
                    inserted_count += 1
                else:
                    skipped_count += 1

        return {
            "total": len(records),
            "inserted": inserted_count,
            "skipped": skipped_count,
        }

    def run(self, db: Session) -> Dict[str, Any]:
        """
        Flujo de ejecución completo del scraper.
        """
        logger.info(f"[{self.name}] Iniciando proceso de ingesta...")
        try:
            raw_items = self.fetch_items()
            logger.info(f"[{self.name}] Elementos descargados: {len(raw_items)}")

            relevant_items = self.filter_relevant(raw_items)
            logger.info(f"[{self.name}] Elementos tras filtrado de relevancia: {len(relevant_items)}")

            enriched_records: List[Dict[str, Any]] = []
            for item in relevant_items:
                try:
                    enriched = self.enrich_item(item)
                    enriched_records.append(enriched)
                except Exception as ex:
                    logger.warning(
                        f"[{self.name}] Fallo al enriquecer elemento '{item.get('title', '')}': {ex}"
                    )

            stats = self.save_records(db, enriched_records)
            logger.info(
                f"[{self.name}] Ingesta finalizada. Total: {stats['total']}, "
                f"Nuevas: {stats['inserted']}, Omitidas (ya existían): {stats['skipped']}"
            )
            return stats
        except Exception as ex:
            logger.error(f"[{self.name}] Error crítico en la ejecución del scraper: {ex}", exc_info=True)
            raise
