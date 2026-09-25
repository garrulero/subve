from datetime import date
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

from db.enums import DestinoGasto, SectorVertical, Territorio

T = TypeVar("T")


class ScorePrimitive(BaseModel):
    """
    Primitiva de puntuación numérica acotada (0.0 a 1.0) con justificación.
    """
    value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Puntuación de confianza o relevancia de 0.0 a 1.0",
    )
    rationale: str = Field(
        ...,
        description="Explicación concisa del razonamiento que sustenta la puntuación",
    )


class ChoicePrimitive(BaseModel, Generic[T]):
    """
    Primitiva para selecciones categóricas tipadas acompañadas de nivel de confianza.
    """
    selected: T = Field(..., description="Opción seleccionada")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Nivel de certeza del modelo en la elección",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Fragmento del texto que respalda la elección",
    )


class NullablePrimitive(BaseModel, Generic[T]):
    """
    Primitiva para atributos que pueden ser determinados, explícitamente nulos, o no aplicables.
    """
    is_present: bool = Field(
        ...,
        description="Indica si el parámetro está contemplado en la convocatoria",
    )
    value: Optional[T] = Field(
        default=None,
        description="Valor extraído en caso de estar presente",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Motivo en caso de no especificarse en la convocatoria",
    )


class ConvocatoriaClassification(BaseModel):
    """
    Esquema integral de salida estructurada generado por el motor de IA
    para transicionar una convocatoria de estado INGESTADA a CLASIFICADA.
    """
    es_empresa_privada: bool = Field(
        ...,
        description="Indica si la subvención está dirigida a pymes, autónomos o empresas privadas (no sólo administración pública)",
    )
    territorio: Territorio = Field(
        ...,
        description="Ámbito geográfico de aplicación (Álava, Bizkaia, Gipuzkoa, autonómica o estatal/UE)",
    )
    sector_vertical: SectorVertical = Field(
        ...,
        description="Sector económico o vertical principal destinatario",
    )
    destino_gasto: DestinoGasto = Field(
        ...,
        description="Finalidad o destino principal del gasto subvencionable",
    )
    intensidad_financiacion: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Porcentaje máximo de ayuda sobre el presupuesto subvencionable (0 a 100%)",
    )
    regimen_concesion: Optional[str] = Field(
        default=None,
        description="Régimen de concesión: 'concurrencia_competitiva', 'concesion_directa', 'orden_solicitud'",
    )
    fecha_cierre: Optional[date] = Field(
        default=None,
        description="Fecha límite para presentación de solicitudes (o null si abierta hasta agotar fondos)",
    )
    resumen_ejecutivo: str = Field(
        ...,
        max_length=1000,
        description="Resumen claro y directo para pymes indicando beneficiarios, cuantía y objetivo",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Etiquetas descriptivas para búsqueda y filtrado secundario",
    )
    relevancia: ScorePrimitive = Field(
        ...,
        description="Evaluación del impacto e interés para el público objetivo del servicio",
    )
