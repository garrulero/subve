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
    agroalimentario_pesca = "agroalimentario_pesca"
    construccion_rehabilitacion = "construccion_rehabilitacion"
    salud_biotecnologia = "salud_biotecnologia"
    transporte_logistica = "transporte_logistica"
    energia_medioambiente = "energia_medioambiente"
    cultura_audiovisual = "cultura_audiovisual"
    cultura_escenicas_eventos = "cultura_escenicas_eventos"
    tic_digitalizacion = "tic_digitalizacion"
    comercio_hosteleria = "comercio_hosteleria"
    servicios_profesionales = "servicios_profesionales"
    multisectorial = "multisectorial"


class TamanoEmpresa(str, Enum):
    """Tamaño de empresa o dimensión del beneficiario."""
    autonomo_individual = "autonomo_individual"
    micro_pyme = "micro_pyme"          # 1 a 9 trabajadores
    pequena_empresa = "pequena_empresa"    # 10 a 49 trabajadores
    mediana_empresa = "mediana_empresa"    # 50 a 249 trabajadores
    gran_empresa = "gran_empresa"          # 250+ trabajadores
    cualquier_tamano = "cualquier_tamano"
    no_aplica = "no_aplica"                # Para particulares / admin


class RegimenConcesion(str, Enum):
    """Régimen de concesión de la ayuda o subvención."""
    concurrencia_competitiva = "concurrencia_competitiva" # Baremo / concurso
    orden_de_llegada = "orden_de_llegada"                 # Concesión sucesiva hasta agotar fondos
    concesion_directa = "concesion_directa"
    no_determinado = "no_determinado"


class DestinoGasto(str, Enum):
    """Tipos y conceptos de gastos subvencionables."""
    activo_fijo_maquinaria = "activo_fijo_maquinaria"
    produccion_obra_cultural = "produccion_obra_cultural"
    digitalizacion_software = "digitalizacion_software"
    eficiencia_energia = "eficiencia_energia"
    contratacion_talento = "contratacion_talento"
    i_mas_d_innovacion = "i_mas_d_innovacion"
    asistencia_accesibilidad_social = "asistencia_accesibilidad_social"
    apoyo_renta_familias = "apoyo_renta_familias"


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


class TipoDocumento(str, Enum):
    """Categoría funcional del documento o anuncio oficial."""
    subvencion_ayuda = "subvencion_ayuda"
    beca_premio = "beca_premio"
    licitacion_contratacion = "licitacion_contratacion"
    empleo_publico = "empleo_publico"
    anuncio_administrativo = "anuncio_administrativo"


class PerfilDestinatario(str, Enum):
    """Perfil beneficiario o grupo destinatario principal de la oportunidad."""
    empresa_pyme = "empresa_pyme"
    autonomo = "autonomo"
    discapacidad_dependencia = "discapacidad_dependencia"
    tercer_sector_asociacion = "tercer_sector_asociacion"
    particulares_general = "particulares_general"
    administracion_publica = "administracion_publica"


