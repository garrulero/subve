from datetime import date
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

from db.enums import DestinoGasto, SectorVertical, Territorio, TipoAyuda

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


class ConvocatoriaEnrichedClassification(BaseModel):
    """
    Esquema exhaustivo y type-safe para la extracción estructurada por IA (modelo jev / Vercel AI Gateway).
    Extrae primitivas tipadas, importes, resúmenes, requisitos, scoring y etiquetas.
    """
    es_empresa_privada: bool = Field(
        ...,
        description=(
            "Estricto: True SOLO si la subvención/ayuda aplica a autónomos, pymes o empresas privadas. "
            "False si es exclusiva para personas físicas individuales, becas académicas personales, "
            "oposiciones/empleo público o entes exclusivamente públicos."
        ),
    )
    resumen_ejecutivo: str = Field(
        ...,
        description="Resumen ejecutivo claro y directo (2-3 frases) orientado a directores de pymes indicando objeto, beneficiarios y cuantía.",
    )
    territorio: Optional[Territorio] = Field(
        default=None,
        description="Ámbito geográfico de aplicación (araba, bizkaia, gipuzkoa, euskadi_autonomica, estatal_ue)",
    )
    sector_vertical: Optional[SectorVertical] = Field(
        default=None,
        description="Sector económico o vertical principal destinatario (industrial_mecanizado, cultura_audiovisual, tic_digitalizacion, etc.)",
    )
    destino_gasto: Optional[DestinoGasto] = Field(
        default=None,
        description="Finalidad principal del gasto subvencionable (activo_fijo_maquinaria, digitalizacion_software, i_mas_d_innovacion, etc.)",
    )
    tipo_ayuda: Optional[TipoAyuda] = Field(
        default=None,
        description="Modalidad de la ayuda: fondo_perdido, prestamo_blando, bonificacion_fiscal, mixta",
    )
    intensidad_financiacion: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Porcentaje máximo de intensidad de ayuda sobre inversión subvencionable (0 a 100%)",
    )
    presupuesto_total: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Presupuesto global total asignado a la partida/convocatoria en euros (o null si no figura)",
    )
    cuantia_maxima_solicitud: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Importe máximo subvencionable por beneficiario/solicitud en euros (o null si no figura)",
    )
    beneficiarios_detalle: str = Field(
        ...,
        description="Descripción detallada de beneficiarios (pymes, autónomos, sectores incluidos/excluidos)",
    )
    requisitos_principales: List[str] = Field(
        default_factory=list,
        description="Lista de condiciones y requisitos clave de elegibilidad",
    )
    gastos_subvencionables: List[str] = Field(
        default_factory=list,
        description="Lista de conceptos y gastos concretos subvencionables",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Lista de etiquetas secundarias para indexación y búsqueda rápida",
    )
    plazo_solicitud_texto: Optional[str] = Field(
        default=None,
        description="Descripción textual del plazo de presentación (ej: '1 mes desde publicación', 'Hasta el 30/10/2026')",
    )
    fecha_cierre: Optional[date] = Field(
        default=None,
        description="Fecha límite exacta de cierre si está determinada (formato YYYY-MM-DD), o null",
    )
    score_relevancia: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Puntuación de 0.0 a 1.0 sobre la relevancia de la ayuda para el tejido empresarial privado de Euskadi",
    )
    score_justificacion: str = Field(
        ...,
        description="Explicación detallada que justifica la puntuación de relevancia asignada y por qué es o no relevante para empresas",
    )


# Alias de compatibilidad hacia atrás
ConvocatoriaClassification = ConvocatoriaEnrichedClassification
