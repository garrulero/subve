import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from config.settings import settings
from db.enums import EstadoConvocatoria
from db.models import Convocatoria
from ai.schemas import ConvocatoriaEnrichedClassification

logger = logging.getLogger(__name__)


class AIClassifierService:
    """
    Servicio de clasificación y extracción de metadatos enriquecidos mediante IA.
    Interactúa con Vercel AI Gateway (o cualquier API compatible con OpenAI) utilizando el modelo 'jev'.
    """

    SYSTEM_PROMPT_TEMPLATE = """Eres un analista experto en legislación, subvenciones y ayudas públicas del País Vasco (BOPV, SPRI, Diputaciones Forales de Bizkaia, Gipuzkoa y Álava, Gobierno Vasco).
Tu función es analizar convocatorias oficiales e identificar aquellas con oportunidad real para empresas privadas, pymes y autónomos.

Debes responder ÚNICAMENTE con un objeto JSON válido que cumpla estrictamente con el siguiente JSON Schema:

{json_schema}

Reglas estrictas de clasificación y extracción:
1. `es_empresa_privada`:
   - Asigna TRUE si la subvención/ayuda otorga financiación, créditos, becas o incentivos a autónomos, pymes, microempresas, talleres, cooperativas o empresas privadas.
   - Asigna FALSE si es exclusiva para empleo público, oposiciones, nombramientos, licencias individuales de obra/agua, becas académicas personales a estudiantes o subvenciones exclusivas a entes públicos y ayuntamientos.
2. `resumen_ejecutivo`: Redacta un resumen ejecutivo de 2 a 3 frases claras orientadas a directores de pymes, explicando objeto, beneficiarios e importe.
3. Extrae importes exactos en euros para `presupuesto_total` y `cuantia_maxima_solicitud` si figuran expresamente (por ejemplo "1.500.000 euros" -> 1500000.0). Si no figuran, asigna null.
4. Extrae la `intensidad_financiacion` como porcentaje entre 0.0 y 100.0 si figura (por ejemplo "70%" -> 70.0).
5. Asigna `territorio`, `sector_vertical`, `destino_gasto` y `tipo_ayuda` según las opciones permitidas del esquema.
6. `score_relevancia`: Valor entre 0.0 y 1.0 según la oportunidad real para pymes. Indica el motivo en `score_justificacion`.
"""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.gateway_url = (gateway_url or settings.AI_GATEWAY_URL).rstrip("/")
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL
        self.temperature = temperature if temperature is not None else settings.AI_TEMPERATURE
        self.timeout_seconds = timeout_seconds or settings.AI_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.AI_MAX_RETRIES

    def _build_system_prompt(self) -> str:
        schema_dict = ConvocatoriaEnrichedClassification.model_json_schema()
        schema_str = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        return self.SYSTEM_PROMPT_TEMPLATE.format(json_schema=schema_str)

    def classify_text(
        self,
        titulo: str,
        organismo: Optional[str],
        texto_crudo: Optional[str],
    ) -> ConvocatoriaEnrichedClassification:
        """
        Envía el título y texto de la convocatoria a la API de IA para obtener
        la clasificación estructurada type-safe.
        """
        system_prompt = self._build_system_prompt()
        clean_text = (texto_crudo or "").strip()[:6000]

        user_content = (
            f"TÍTULO DE LA CONVOCATORIA:\n{titulo}\n\n"
            f"ORGANISMO EMISOR:\n{organismo or 'No especificado'}\n\n"
            f"TEXTO OFICIAL DEL BOLETÍN:\n{clean_text}"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        url = f"{self.gateway_url}/chat/completions"
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"[AIClassifierService] Enviando petición a {url} (modelo '{self.model}', intento {attempt}/{self.max_retries})..."
                )
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(url, headers=headers, json=payload)

                    if resp.status_code in (429, 500, 502, 503, 504):
                        sleep_time = (2 ** (attempt - 1)) * 1.5
                        logger.warning(
                            f"[AIClassifierService] Error HTTP {resp.status_code} de la API de IA. "
                            f"Reintentando en {sleep_time:.1f}s (intento {attempt}/{self.max_retries})..."
                        )
                        time.sleep(sleep_time)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError(f"Respuesta inválida de la API de IA (sin choices): {data}")

                    content_str = choices[0]["message"]["content"]
                    return ConvocatoriaEnrichedClassification.model_validate_json(content_str)

            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, Exception) as ex:
                last_exception = ex
                sleep_time = (2 ** (attempt - 1)) * 1.5
                logger.warning(
                    f"[AIClassifierService] Intento {attempt}/{self.max_retries} falló: {ex}. "
                    f"Reintentando en {sleep_time:.1f}s..."
                )
                if attempt < self.max_retries:
                    time.sleep(sleep_time)

        raise RuntimeError(
            f"Fallo irrecuperable al clasificar con IA tras {self.max_retries} intentos: {last_exception}"
        )

    def process_convocatoria(
        self,
        db: Session,
        convocatoria: Convocatoria,
    ) -> Convocatoria:
        """
        Procesa una convocatoria individual y actualiza la base de datos de forma atómica.
        """
        try:
            classification = self.classify_text(
                titulo=convocatoria.titulo,
                organismo=convocatoria.organismo,
                texto_crudo=convocatoria.texto_crudo,
            )

            now = datetime.now(timezone.utc)
            convocatoria.ai_model = self.model
            convocatoria.ai_processed_at = now
            convocatoria.es_empresa_privada = classification.es_empresa_privada
            convocatoria.score_relevancia = classification.score_relevancia
            convocatoria.score_justificacion = classification.score_justificacion

            if classification.es_empresa_privada:
                convocatoria.estado = EstadoConvocatoria.CLASIFICADA
                convocatoria.resumen_ejecutivo = classification.resumen_ejecutivo
                convocatoria.territorio = classification.territorio
                convocatoria.sector_vertical = classification.sector_vertical
                convocatoria.destino_gasto = classification.destino_gasto
                convocatoria.tipo_ayuda = classification.tipo_ayuda
                convocatoria.intensidad_financiacion = classification.intensidad_financiacion
                convocatoria.presupuesto_total = classification.presupuesto_total
                convocatoria.cuantia_maxima_solicitud = classification.cuantia_maxima_solicitud
                convocatoria.beneficiarios_detalle = classification.beneficiarios_detalle
                convocatoria.requisitos_principales = classification.requisitos_principales
                convocatoria.gastos_subvencionables = classification.gastos_subvencionables
                convocatoria.tags = classification.tags
                convocatoria.plazo_solicitud_texto = classification.plazo_solicitud_texto
                convocatoria.fecha_cierre = classification.fecha_cierre
            else:
                convocatoria.estado = EstadoConvocatoria.DESCARTADA

            db.commit()
            db.refresh(convocatoria)
            return convocatoria

        except Exception as ex:
            db.rollback()
            logger.error(
                f"[AIClassifierService] Error procesando convocatoria ID={convocatoria.id} "
                f"({convocatoria.id_origen}): {ex}",
                exc_info=True,
            )
            try:
                convocatoria.estado = EstadoConvocatoria.ERROR
                convocatoria.score_justificacion = f"Error durante clasificación con IA: {str(ex)}"
                db.commit()
            except Exception:
                db.rollback()
            raise

    def process_batch(
        self,
        db: Session,
        limit: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, int]:
        """
        Procesa un lote de convocatorias en la base de datos de forma secuencial y atómica.
        """
        query = db.query(Convocatoria)
        if not force:
            query = query.filter(Convocatoria.estado == EstadoConvocatoria.INGESTADA)
        query = query.order_by(Convocatoria.created_at.desc())

        if limit and limit > 0:
            query = query.limit(limit)

        convocatorias = query.all()
        total = len(convocatorias)
        logger.info(f"[AIClassifierService] Iniciando procesamiento de {total} convocatorias...")

        stats = {
            "total": total,
            "clasificadas": 0,
            "descartadas": 0,
            "errores": 0,
        }

        for idx, convocatoria in enumerate(convocatorias, start=1):
            logger.info(
                f"[AIClassifierService] [{idx}/{total}] Clasificando ID={convocatoria.id} "
                f"('{convocatoria.titulo[:60]}...')"
            )
            try:
                processed = self.process_convocatoria(db, convocatoria)
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
