from enum import Enum


class EstadoConvocatoria(str, Enum):
    """
    Máquina de estados para el ciclo de vida de una convocatoria de subvención.
    """
    INGESTADA = "INGESTADA"      # Datos crudos del boletín almacenados en DB
    CLASIFICADA = "CLASIFICADA"  # Evaluada por IA, primitivas tipadas almacenadas
    MATCHED = "MATCHED"          # Emparejada con clientes activos compatibles
    NOTIFICADA = "NOTIFICADA"    # Token generado y mensaje enviado al cliente
    DESCARTADA = "DESCARTADA"    # No relevante para empresas o fuera de alcance
    ERROR = "ERROR"              # Error durante la ingesta o procesamiento


class Territorio(str, Enum):
    """Ámbito territorial geográfico de aplicación de la convocatoria."""
    araba = "araba"
    bizkaia = "bizkaia"
    gipuzkoa = "gipuzkoa"
    euskadi_autonomica = "euskadi_autonomica"
    estatal_ue = "estatal_ue"


class SectorVertical(str, Enum):
    """Sectores verticales y actividades económicas de pymes y talleres."""
    industrial_mecanizado = "industrial_mecanizado"
    cultura_audiovisual = "cultura_audiovisual"
    cultura_escenicas_eventos = "cultura_escenicas_eventos"
    tic_digitalizacion = "tic_digitalizacion"
    comercio_hosteleria = "comercio_hosteleria"
    multisectorial = "multisectorial"


class DestinoGasto(str, Enum):
    """Tipos y conceptos de gastos subvencionables."""
    activo_fijo_maquinaria = "activo_fijo_maquinaria"
    produccion_obra_cultural = "produccion_obra_cultural"
    digitalizacion_software = "digitalizacion_software"
    eficiencia_energia = "eficiencia_energia"
    contratacion_talento = "contratacion_talento"
    i_mas_d_innovacion = "i_mas_d_innovacion"


class CanalNotificacion(str, Enum):
    """Canales de envío para notificaciones a clientes."""
    telegram = "telegram"
    email = "email"


class TipoAyuda(str, Enum):
    """Modalidad o tipo de financiación de la ayuda."""
    fondo_perdido = "fondo_perdido"
    prestamo_blando = "prestamo_blando"
    bonificacion_fiscal = "bonificacion_fiscal"
    mixta = "mixta"

