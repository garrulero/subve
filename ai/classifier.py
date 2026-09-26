import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from config.settings import settings
from db.enums import (
    DestinoGasto,
    EstadoConvocatoria,
    PerfilDestinatario,
    SectorVertical,
    Territorio,
    TipoAyuda,
    TipoDocumento,
)
from db.models import Convocatoria

logger = logging.getLogger(__name__)


class AIClassifierService:
    """
    Servicio de clasificación inteligente utilizando la API nativa de TypeSafe AI ('jev')
    a través de Vercel AI Gateway (endpoint /typesafe/v1/systemone).
    """

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        raw_url = (gateway_url or settings.AI_GATEWAY_URL).rstrip("/")
        # Normalizar para asegurar que apunta a /typesafe/v1/systemone
        if "typesafe/v1/systemone" not in raw_url:
            base_host = raw_url.replace("/v1", "")
            self.endpoint_url = f"{base_host}/typesafe/v1/systemone"
        else:
            self.endpoint_url = raw_url

        self.api_key = api_key or settings.AI_API_KEY
        self.model = "typesafe-ai/jev" if (model or settings.AI_MODEL) == "jev" else (model or settings.AI_MODEL)
        self.timeout_seconds = timeout_seconds or settings.AI_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.AI_MAX_RETRIES

    def _build_payload(self, titulo: str, organismo: Optional[str], texto_crudo: Optional[str]) -> Dict[str, Any]:
        """Construye el payload nativo SystemOne con state y questions tipadas."""
        clean_text = (texto_crudo or "").strip()[:6000]
        state = (
            f"TÍTULO DE LA CONVOCATORIA:\n{titulo}\n\n"
            f"ORGANISMO EMISOR:\n{organismo or 'No especificado'}\n\n"
            f"TEXTO OFICIAL DEL BOLETÍN:\n{clean_text}"
        )

        return {
            "model": self.model,
            "state": state,
            "questions": {
                "tipo_documento": {
                    "type": "choice",
                    "instructions": "¿Qué tipología de documento o anuncio administrativo es?",
                    "criteria": {
                        "subvencion_ayuda": "Subvención, ayuda económica o partida de financiación",
                        "beca_premio": "Beca individual de estudios, formación o premio",
                        "licitacion_contratacion": "Licitación pública, pliego o concurso de contratación",
                        "empleo_publico": "Oferta de empleo público, oposición, tribunal o nombramiento",
                        "anuncio_administrativo": "Trámite administrativo general sin dotación ni ayuda económica",
                    },
                },
                "perfil_destinatario": {
                    "type": "choice",
                    "instructions": "¿A qué colectivo o beneficiario principal va dirigida la oportunidad?",
                    "criteria": {
                        "empresa_pyme": "Pymes, micropymes, talleres y empresas privadas",
                        "autonomo": "Trabajadores autónomos y profesionales independientes",
                        "discapacidad_dependencia": "Personas con discapacidad, dependencia, movilidad reducida o accesibilidad",
                        "tercer_sector_asociacion": "ONGs, fundaciones, federaciones y entidades sin ánimo de lucro",
                        "particulares_general": "Particulares, familias, jóvenes o estudiantes",
                        "administracion_publica": "Exclusivo para ayuntamientos y entes de la administración pública",
                    },
                },
                "territorio": {
                    "type": "choice",
                    "instructions": "¿Cuál es el ámbito territorial principal de aplicación?",
                    "criteria": {
                        "araba": "Álava / Araba",
                        "bizkaia": "Bizkaia",
                        "gipuzkoa": "Gipuzkoa",
                        "euskadi_autonomica": "Comunidad Autónoma del País Vasco en su conjunto",
                        "estatal_ue": "Ámbito estatal de España o de la Unión Europea",
                    },
                },
                "sector_vertical": {
                    "type": "choice",
                    "instructions": "¿A qué sector o actividad corresponde principalmente?",
                    "criteria": {
                        "industrial_mecanizado": "Sector industrial, manufactura, máquina herramienta y talleres",
                        "cultura_audiovisual": "Cultura, cine, creación audiovisual y medios",
                        "cultura_escenicas_eventos": "Artes escénicas, música en vivo y eventos",
                        "tic_digitalizacion": "Software, telecomunicaciones y tecnologías de la información",
                        "comercio_hosteleria": "Comercio minorista, turismo y hostelería",
                        "multisectorial": "Multisectorial, social o aplicable a cualquier actividad",
                    },
                },
                "destino_gasto": {
                    "type": "choice",
                    "instructions": "¿Cuál es el destino o finalidad del gasto subvencionable?",
                    "criteria": {
                        "activo_fijo_maquinaria": "Inversión en maquinaria, equipos e infraestructura física",
                        "produccion_obra_cultural": "Creación o producción artística y cultural",
                        "digitalizacion_software": "Software, digitalización y herramientas tecnológicas",
                        "eficiencia_energia": "Eficiencia energética, descarbonización y renovables",
                        "contratacion_talento": "Contratación laboral y formación de personal",
                        "i_mas_d_innovacion": "I+D, prototipos e investigación aplicada",
                        "asistencia_accesibilidad_social": "Asistencia, eliminación de barreras y accesibilidad para discapacidad",
                        "apoyo_renta_familias": "Ayuda económica directa, bono o apoyo a familias y personas",
                    },
                },
                "tipo_ayuda": {
                    "type": "choice",
                    "instructions": "¿Qué modalidad de ayuda o financiación ofrece?",
                    "criteria": {
                        "fondo_perdido": "Subvención directa a fondo perdido (no reembolsable)",
                        "prestamo_blando": "Préstamo o crédito en condiciones ventajosas / bonificadas",
                        "bonificacion_fiscal": "Deducción o incentivo fiscal",
                        "mixta": "Combinación mixta de subvención y préstamo",
                    },
                },
            },
        }

    def classify_convocatoria_raw(self, titulo: str, organismo: Optional[str], texto_crudo: Optional[str]) -> Dict[str, Any]:
        """Envía el state y questions a /typesafe/v1/systemone y retorna las respuestas de jev."""
        payload = self._build_payload(titulo, organismo, texto_crudo)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"[AIClassifierService] Consultando TypeSafe 'jev' en {self.endpoint_url} "
                    f"(intento {attempt}/{self.max_retries})..."
                )
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(self.endpoint_url, headers=headers, json=payload)

                    if resp.status_code in (429, 500, 502, 503, 504):
                        sleep_time = (2 ** (attempt - 1)) * 1.5
                        logger.warning(
                            f"[AIClassifierService] Código HTTP {resp.status_code}. "
                            f"Reintentando en {sleep_time:.1f}s..."
                        )
                        time.sleep(sleep_time)
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    answers = data.get("answers", {})
                    if not answers:
                        raise ValueError(f"Respuesta inválida de 'jev' (sin answers): {data}")
                    return answers

            except Exception as ex:
                last_exception = ex
                sleep_time = (2 ** (attempt - 1)) * 1.5
                logger.warning(
                    f"[AIClassifierService] Fallo en intento {attempt}/{self.max_retries}: {ex}. "
                    f"Reintentando en {sleep_time:.1f}s..."
                )
                if attempt < self.max_retries:
                    time.sleep(sleep_time)

        raise RuntimeError(
            f"Fallo irrecuperable al clasificar con 'jev' tras {self.max_retries} intentos: {last_exception}"
        )

    def process_convocatoria(self, db: Session, convocatoria: Convocatoria) -> Convocatoria:
        """Clasifica una convocatoria individual y actualiza la base de datos de forma atómica."""
        try:
            answers = self.classify_convocatoria_raw(
                titulo=convocatoria.titulo,
                organismo=convocatoria.organismo,
                texto_crudo=convocatoria.texto_crudo,
            )

            # Extraer opciones elegidas de las primitivas choice de jev
            tipo_doc_val = answers.get("tipo_documento", {}).get("choice", "anuncio_administrativo")
            perfil_val = answers.get("perfil_destinatario", {}).get("choice", "particulares_general")
            territorio_val = answers.get("territorio", {}).get("choice", "euskadi_autonomica")
            sector_val = answers.get("sector_vertical", {}).get("choice", "multisectorial")
            destino_val = answers.get("destino_gasto", {}).get("choice", "asistencia_accesibilidad_social")
            tipo_ayuda_val = answers.get("tipo_ayuda", {}).get("choice", "fondo_perdido")
            confidence = float(answers.get("perfil_destinatario", {}).get("confidence", 0.8))

            now = datetime.now(timezone.utc)
            convocatoria.ai_model = "typesafe-ai/jev"
            convocatoria.ai_processed_at = now
            convocatoria.tipo_documento = TipoDocumento(tipo_doc_val)
            convocatoria.perfil_destinatario = PerfilDestinatario(perfil_val)
            convocatoria.territorio = Territorio(territorio_val)
            convocatoria.sector_vertical = SectorVertical(sector_val)
            convocatoria.destino_gasto = DestinoGasto(destino_val)
            convocatoria.tipo_ayuda = TipoAyuda(tipo_ayuda_val)

            # Marcar es_empresa_privada si el perfil es empresa o autónomo
            es_empresa = perfil_val in ("empresa_pyme", "autonomo")
            convocatoria.es_empresa_privada = es_empresa
            convocatoria.score_relevancia = confidence

            # Solo descartamos anuncios meramente burocráticos sin ayuda económica
            if tipo_doc_val == "anuncio_administrativo":
                convocatoria.estado = EstadoConvocatoria.DESCARTADA
                convocatoria.score_justificacion = "Trámite administrativo general sin dotación de ayuda económica."
            else:
                convocatoria.estado = EstadoConvocatoria.CLASIFICADA
                convocatoria.resumen_ejecutivo = (
                    f"Convocatoria de {tipo_ayuda_val.replace('_', ' ')} dirigida a "
                    f"{perfil_val.replace('_', ' ')} en el ámbito de {territorio_val.replace('_', ' ')} "
                    f"para {destino_val.replace('_', ' ')}."
                )
                convocatoria.tags = [tipo_doc_val, perfil_val, territorio_val, tipo_ayuda_val]
                convocatoria.score_justificacion = (
                    f"Clasificada con 'jev' para perfil '{perfil_val}' con confianza {confidence:.2f}."
                )

            db.commit()
            db.refresh(convocatoria)
            return convocatoria

        except Exception as ex:
            db.rollback()
            logger.error(
                f"[AIClassifierService] Error procesando Convocatoria ID={convocatoria.id} "
                f"({convocatoria.id_origen}): {ex}",
                exc_info=True,
            )
            try:
                convocatoria.estado = EstadoConvocatoria.ERROR
                convocatoria.score_justificacion = f"Error en clasificación con 'jev': {str(ex)}"
                db.commit()
            except Exception:
                db.rollback()
            raise

    def process_batch(self, db: Session, limit: Optional[int] = None, force: bool = False) -> Dict[str, int]:
        """Procesa un lote de convocatorias secuencial y atómicamente."""
        query = db.query(Convocatoria)
        if not force:
            query = query.filter(
                Convocatoria.estado.in_([
                    EstadoConvocatoria.INGESTADA,
                    EstadoConvocatoria.ERROR,
                ])
            )
        query = query.order_by(Convocatoria.created_at.desc())

        if limit and limit > 0:
            query = query.limit(limit)

        convocatorias = query.all()
        total = len(convocatorias)
        logger.info(f"[AIClassifierService] Procesando lote de {total} convocatorias con TypeSafe 'jev'...")

        stats = {"total": total, "clasificadas": 0, "descartadas": 0, "errores": 0}

        for idx, conv in enumerate(convocatorias, start=1):
            logger.info(f"[AIClassifierService] [{idx}/{total}] Evaluando ID={conv.id} ('{conv.titulo[:60]}...')")
            try:
                processed = self.process_convocatoria(db, conv)
                if processed.estado == EstadoConvocatoria.CLASIFICADA:
                    stats["clasificadas"] += 1
                elif processed.estado == EstadoConvocatoria.DESCARTADA:
                    stats["descartadas"] += 1
                else:
                    stats["errores"] += 1
            except Exception:
                stats["errores"] += 1

        logger.info(
            f"[AIClassifierService] Lote completado. Total: {stats['total']}, "
            f"Clasificadas: {stats['clasificadas']}, Descartadas: {stats['descartadas']}, "
            f"Errores: {stats['errores']}"
        )
        return stats