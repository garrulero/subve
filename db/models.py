from datetime import date, datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.enums import (
    CanalNotificacion,
    DestinoGasto,
    EstadoConvocatoria,
    SectorVertical,
    Territorio,
    TipoAyuda,
)


class Convocatoria(Base):
    """
    Modelo representativo de una convocatoria pública de subvención o ayuda.
    Gestionado por la máquina de estados desde la ingesta cruda hasta la notificación.
    """
    __tablename__ = "convocatorias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_origen: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Identificador unívoco del boletín o portal de origen",
    )
    fuente: Mapped[str] = mapped_column(
        String(50),
        default="BOPV",
        nullable=False,
        comment="Boletín o fuente oficial (p. ej. BOPV, BOB, BOTHA)",
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    organismo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url_oficial: Mapped[str] = mapped_column(Text, nullable=False)
    texto_crudo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_publicacion: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # Estado de la máquina de estados
    estado: Mapped[EstadoConvocatoria] = mapped_column(
        SQLEnum(EstadoConvocatoria, native_enum=False),
        default=EstadoConvocatoria.INGESTADA,
        nullable=False,
        index=True,
    )

    # Primitivas tipadas de clasificación (rellenadas en estado CLASIFICADA)
    es_empresa_privada: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    territorio: Mapped[Optional[Territorio]] = mapped_column(
        SQLEnum(Territorio, native_enum=False),
        nullable=True,
        index=True,
    )
    sector_vertical: Mapped[Optional[SectorVertical]] = mapped_column(
        SQLEnum(SectorVertical, native_enum=False),
        nullable=True,
        index=True,
    )
    destino_gasto: Mapped[Optional[DestinoGasto]] = mapped_column(
        SQLEnum(DestinoGasto, native_enum=False),
        nullable=True,
        index=True,
    )
    intensidad_financiacion: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Porcentaje de intensidad máxima de financiación (0 a 100)",
    )
    regimen_concesion: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Concurrencia competitiva o concesión directa",
    )
    fecha_cierre: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Columnas de clasificación enriquecida con IA (Fase 2)
    resumen_ejecutivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    presupuesto_total: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Presupuesto global total asignado a la partida",
    )
    cuantia_maxima_solicitud: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Tope máximo subvencionable por beneficiario",
    )
    tipo_ayuda: Mapped[Optional[TipoAyuda]] = mapped_column(
        SQLEnum(TipoAyuda, native_enum=False),
        nullable=True,
        index=True,
    )
    beneficiarios_detalle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requisitos_principales: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    gastos_subvencionables: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    score_relevancia: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_justificacion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plazo_solicitud_texto: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ai_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auditoría temporal
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relaciones
    notificaciones: Mapped[List["Notificacion"]] = relationship(
        "Notificacion",
        back_populates="convocatoria",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Convocatoria(id={self.id}, id_origen='{self.id_origen}', estado='{self.estado}')>"


class Cliente(Base):
    """
    Empresa, pyme o taller destinatario potencial de subvenciones.
    """
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre_comercial: Mapped[str] = mapped_column(String(255), nullable=False)
    razon_social: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cif: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    territorio: Mapped[Territorio] = mapped_column(
        SQLEnum(Territorio, native_enum=False),
        default=Territorio.araba,
        nullable=False,
        index=True,
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    intereses: Mapped[List["InteresCliente"]] = relationship(
        "InteresCliente",
        back_populates="cliente",
        cascade="all, delete-orphan",
    )
    notificaciones: Mapped[List["Notificacion"]] = relationship(
        "Notificacion",
        back_populates="cliente",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Cliente(id={self.id}, nombre='{self.nombre_comercial}', territorio='{self.territorio}')>"


class InteresCliente(Base):
    """
    Perfil de interés granular (sector y destino de gasto) por cliente.
    """
    __tablename__ = "intereses_cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sector_vertical: Mapped[SectorVertical] = mapped_column(
        SQLEnum(SectorVertical, native_enum=False),
        nullable=False,
        index=True,
    )
    destino_gasto: Mapped[DestinoGasto] = mapped_column(
        SQLEnum(DestinoGasto, native_enum=False),
        nullable=False,
        index=True,
    )

    # Relaciones
    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="intereses")

    __table_args__ = (
        Index("ix_interes_cliente_matching", "cliente_id", "sector_vertical", "destino_gasto", unique=True),
    )


class Notificacion(Base):
    """
    Registro de notificación enviada a un cliente sobre una convocatoria específica.
    Contiene el token único de tracking.
    """
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    convocatoria_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("convocatorias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_tracking: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Token unívoco generado para el enlace de tracking",
    )
    canal: Mapped[CanalNotificacion] = mapped_column(
        SQLEnum(CanalNotificacion, native_enum=False),
        default=CanalNotificacion.telegram,
        nullable=False,
    )
    enviada_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones
    convocatoria: Mapped["Convocatoria"] = relationship("Convocatoria", back_populates="notificaciones")
    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="notificaciones")
    clicks: Mapped[List["ClickTracking"]] = relationship(
        "ClickTracking",
        back_populates="notificacion",
        cascade="all, delete-orphan",
    )


class ClickTracking(Base):
    """
    Auditoría y telemetría de clics sobre enlaces de notificaciones.
    """
    __tablename__ = "click_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notificacion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("notificaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Hash SHA-256 anonimizado de la dirección IP",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relaciones
    notificacion: Mapped["Notificacion"] = relationship("Notificacion", back_populates="clicks")
