import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from config.settings import settings
from db.base import get_db
from db.enums import (
    DestinoGasto,
    EstadoConvocatoria,
    PerfilDestinatario,
    RegimenConcesion,
    SectorVertical,
    TamanoEmpresa,
    Territorio,
    TipoAyuda,
    TipoDocumento,
)
from db.models import Convocatoria
from ai.classifier import AIClassifierService
from scrapers.bopv import BOPVScraper

logger = logging.getLogger("web.admin")

admin_router = APIRouter(prefix="/api/admin", tags=["Administración Web"])


class ScrapeActionRequest(BaseModel):
    days: int = 1


class ClassifyActionRequest(BaseModel):
    limit: Optional[int] = None
    force: bool = False


def _serialize_convocatoria(c: Convocatoria) -> Dict[str, Any]:
    """Convierte una instancia de Convocatoria en un diccionario JSON-safe."""
    return {
        "id": c.id,
        "id_origen": c.id_origen,
        "fuente": c.fuente,
        "titulo": c.titulo,
        "organismo": c.organismo,
        "url_oficial": c.url_oficial,
        "texto_crudo": c.texto_crudo,
        "fecha_publicacion": c.fecha_publicacion.isoformat() if c.fecha_publicacion else None,
        "estado": c.estado.value if hasattr(c.estado, "value") else str(c.estado),
        "es_empresa_privada": c.es_empresa_privada,
        "tipo_documento": c.tipo_documento.value if c.tipo_documento and hasattr(c.tipo_documento, "value") else (str(c.tipo_documento) if c.tipo_documento else None),
        "perfil_destinatario": c.perfil_destinatario.value if c.perfil_destinatario and hasattr(c.perfil_destinatario, "value") else (str(c.perfil_destinatario) if c.perfil_destinatario else None),
        "territorio": c.territorio.value if c.territorio and hasattr(c.territorio, "value") else (str(c.territorio) if c.territorio else None),
        "sector_vertical": c.sector_vertical.value if c.sector_vertical and hasattr(c.sector_vertical, "value") else (str(c.sector_vertical) if c.sector_vertical else None),
        "destino_gasto": c.destino_gasto.value if c.destino_gasto and hasattr(c.destino_gasto, "value") else (str(c.destino_gasto) if c.destino_gasto else None),
        "tipo_ayuda": c.tipo_ayuda.value if c.tipo_ayuda and hasattr(c.tipo_ayuda, "value") else (str(c.tipo_ayuda) if c.tipo_ayuda else None),
        "intensidad_financiacion": c.intensidad_financiacion,
        "tamano_empresa": c.tamano_empresa.value if c.tamano_empresa and hasattr(c.tamano_empresa, "value") else (str(c.tamano_empresa) if c.tamano_empresa else None),
        "regimen_concesion": c.regimen_concesion.value if c.regimen_concesion and hasattr(c.regimen_concesion, "value") else (str(c.regimen_concesion) if c.regimen_concesion else None),
        "fecha_apertura": c.fecha_apertura.isoformat() if c.fecha_apertura else None,
        "fecha_cierre": c.fecha_cierre.isoformat() if c.fecha_cierre else None,
        "resumen_ejecutivo": c.resumen_ejecutivo,
        "presupuesto_total": c.presupuesto_total,
        "cuantia_maxima_solicitud": c.cuantia_maxima_solicitud,
        "beneficiarios_detalle": c.beneficiarios_detalle,
        "requisitos_principales": c.requisitos_principales,
        "gastos_subvencionables": c.gastos_subvencionables,
        "tags": c.tags,
        "score_relevancia": c.score_relevancia,
        "score_justificacion": c.score_justificacion,
        "plazo_solicitud_texto": c.plazo_solicitud_texto,
        "ai_model": c.ai_model,
        "ai_processed_at": c.ai_processed_at.isoformat() if c.ai_processed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@admin_router.get("/stats", summary="Obtiene estadísticas globales del sistema")
def get_stats(db: Session = Depends(get_db)):
    """Devuelve métricas agregadas por estado, perfil destinatario, tipo de documento y fechas de auditoría."""
    total = db.query(func.count(Convocatoria.id)).scalar() or 0

    # Agrupación por estado
    estado_counts = (
        db.query(Convocatoria.estado, func.count(Convocatoria.id))
        .group_by(Convocatoria.estado)
        .all()
    )
    estados_dict = {e.name if hasattr(e, "name") else str(e): count for e, count in estado_counts}
    for est in EstadoConvocatoria:
        if est.name not in estados_dict:
            estados_dict[est.name] = 0

    # Agrupación por perfil destinatario
    perfil_counts = (
        db.query(Convocatoria.perfil_destinatario, func.count(Convocatoria.id))
        .group_by(Convocatoria.perfil_destinatario)
        .all()
    )
    perfiles_dict = {}
    for perf, count in perfil_counts:
        key = perf.name if perf and hasattr(perf, "name") else (str(perf) if perf else "sin_clasificar")
        perfiles_dict[key] = count

    # Agrupación por tipo documento
    tipo_doc_counts = (
        db.query(Convocatoria.tipo_documento, func.count(Convocatoria.id))
        .group_by(Convocatoria.tipo_documento)
        .all()
    )
    tipos_doc_dict = {}
    for tdoc, count in tipo_doc_counts:
        key = tdoc.name if tdoc and hasattr(tdoc, "name") else (str(tdoc) if tdoc else "sin_clasificar")
        tipos_doc_dict[key] = count

    # Última ingesta y clasificación
    last_created = db.query(func.max(Convocatoria.created_at)).scalar()
    last_ai = db.query(func.max(Convocatoria.ai_processed_at)).scalar()

    return {
        "total_convocatorias": total,
        "estados": estados_dict,
        "perfiles": perfiles_dict,
        "tipos_documento": tipos_doc_dict,
        "ultima_ingesta": last_created.isoformat() if hasattr(last_created, "isoformat") else (str(last_created) if last_created else None),
        "ultima_clasificacion": last_ai.isoformat() if hasattr(last_ai, "isoformat") else (str(last_ai) if last_ai else None),
    }


@admin_router.get("/convocatorias", summary="Listado completo y filtrado de convocatorias")
def get_convocatorias(
    search: Optional[str] = Query(None, description="Búsqueda libre por título, organismo o id_origen"),
    estado: Optional[EstadoConvocatoria] = Query(None),
    perfil_destinatario: Optional[PerfilDestinatario] = Query(None),
    tipo_documento: Optional[TipoDocumento] = Query(None),
    territorio: Optional[Territorio] = Query(None),
    sector_vertical: Optional[SectorVertical] = Query(None),
    tamano_empresa: Optional[TamanoEmpresa] = Query(None),
    regimen_concesion: Optional[RegimenConcesion] = Query(None),
    solo_abiertas: bool = Query(False, description="Filtra convocatorias con fecha de cierre vigente o nula"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Consulta convocatorias con filtrado dinámico multi-criterio y soporte para paginación."""
    query = db.query(Convocatoria)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Convocatoria.titulo.ilike(term),
                Convocatoria.organismo.ilike(term),
                Convocatoria.id_origen.ilike(term),
            )
        )

    if estado:
        query = query.filter(Convocatoria.estado == estado)
    if perfil_destinatario:
        query = query.filter(Convocatoria.perfil_destinatario == perfil_destinatario)
    if tipo_documento:
        query = query.filter(Convocatoria.tipo_documento == tipo_documento)
    if territorio:
        query = query.filter(Convocatoria.territorio == territorio)
    if sector_vertical:
        query = query.filter(Convocatoria.sector_vertical == sector_vertical)
    if tamano_empresa:
        query = query.filter(Convocatoria.tamano_empresa == tamano_empresa)
    if regimen_concesion:
        query = query.filter(Convocatoria.regimen_concesion == regimen_concesion)
    if solo_abiertas:
        hoy = date.today()
        query = query.filter(or_(Convocatoria.fecha_cierre >= hoy, Convocatoria.fecha_cierre.is_(None)))

    total_filtered = query.count()
    results = query.order_by(Convocatoria.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total_filtered,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_convocatoria(c) for c in results],
    }


@admin_router.post("/convocatorias/{convocatoria_id}/reclassify", summary="Reclasifica una convocatoria individual")
def reclassify_convocatoria(convocatoria_id: int, db: Session = Depends(get_db)):
    """Fuerza la reclasificación inmediata mediante IA ('jev') de una convocatoria específica."""
    conv = db.query(Convocatoria).filter(Convocatoria.id == convocatoria_id).first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Convocatoria con ID {convocatoria_id} no encontrada",
        )

    service = AIClassifierService()
    try:
        updated = service.process_convocatoria(db, conv)
        return {
            "status": "success",
            "message": f"Convocatoria ID {convocatoria_id} reevaluada con éxito.",
            "item": _serialize_convocatoria(updated),
        }
    except Exception as ex:
        logger.error(f"Error al reclasificar convocatoria ID {convocatoria_id}: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la clasificación con IA: {str(ex)}",
        )


@admin_router.post("/actions/scrape", summary="Dispara el proceso de ingesta BOPV")
def action_scrape(payload: ScrapeActionRequest, db: Session = Depends(get_db)):
    """Ejecuta el scraper del Boletín Oficial del País Vasco (BOPV) para N días laborables."""
    try:
        scraper = BOPVScraper(days=payload.days)
        stats = scraper.run(db)
        return {
            "status": "success",
            "message": f"Ingesta completada para {payload.days} día(s).",
            "stats": stats,
        }
    except Exception as ex:
        logger.error(f"Error durante ejecución del scraper BOPV: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo en la ingesta del BOPV: {str(ex)}",
        )


@admin_router.post("/actions/classify", summary="Dispara la clasificación por lotes con IA")
def action_classify(payload: ClassifyActionRequest, db: Session = Depends(get_db)):
    """Ejecuta el clasificador TypeSafe 'jev' sobre el lote de convocatorias pendientes o todas (--force)."""
    try:
        service = AIClassifierService()
        stats = service.process_batch(db, limit=payload.limit, force=payload.force)
        return {
            "status": "success",
            "message": "Proceso de clasificación por lote completado.",
            "stats": stats,
        }
    except Exception as ex:
        logger.error(f"Error durante clasificación por lotes con IA: {ex}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo en clasificación por lotes: {str(ex)}",
        )


@admin_router.get("/logs/{log_name}", summary="Lee e inspecciona archivos de log formateados")
def get_log_file(
    log_name: str,
    lines: int = Query(200, ge=10, le=2000),
):
    """Retorna los registros recientes del archivo de log especificado con análisis estructurado."""
    allowed_files = {"app.log", "errors.log", "classifier_errors.log", "scrapers.log"}
    if log_name not in allowed_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nombre de log no permitido. Válidos: {', '.join(allowed_files)}",
        )

    log_path: Path = settings.LOGS_DIR / log_name
    if not log_path.exists():
        return {
            "log_name": log_name,
            "total_entries": 0,
            "entries": [],
            "message": f"El archivo {log_name} aún no se ha creado.",
        }

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()

        # Tomar las últimas N líneas
        tail_lines = raw_lines[-lines:] if len(raw_lines) > lines else raw_lines

        # Regex para cabecera de log: 2026-09-26 10:42:27,626 [ERROR] [ai.classifier] [classifier.py:240]: ...
        log_header_pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]:\s+(.*)$"
        )

        entries: List[Dict[str, Any]] = []
        current_entry: Optional[Dict[str, Any]] = None

        for line in tail_lines:
            line_str = line.rstrip("\n")
            match = log_header_pattern.match(line_str)
            if match:
                if current_entry:
                    entries.append(current_entry)
                current_entry = {
                    "timestamp": match.group(1),
                    "level": match.group(2).upper(),
                    "logger": match.group(3),
                    "location": match.group(4),
                    "message": match.group(5),
                    "traceback": [],
                }
            else:
                if current_entry:
                    current_entry["traceback"].append(line_str)
                else:
                    # Traza huérfana al principio del corte
                    current_entry = {
                        "timestamp": "",
                        "level": "INFO",
                        "logger": "sys",
                        "location": "",
                        "message": line_str,
                        "traceback": [],
                    }

        if current_entry:
            entries.append(current_entry)

        return {
            "log_name": log_name,
            "total_entries": len(entries),
            "entries": entries,
        }

    except Exception as ex:
        logger.error(f"Error leyendo archivo de log {log_name}: {ex}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error leyendo log: {str(ex)}",
        )
