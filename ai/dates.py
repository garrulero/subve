import re
from datetime import date, timedelta
from typing import Optional, Tuple

MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def extract_dates_and_deadlines(
    texto_crudo: Optional[str],
    fecha_publicacion: Optional[date] = None,
) -> Tuple[Optional[date], Optional[date], Optional[str]]:
    """
    Extrae deterministamente (fecha_apertura, fecha_cierre, plazo_solicitud_texto)
    analizando patrones normativos habituales del BOPV y boletines oficiales.
    """
    if not texto_crudo:
        f_ap = (fecha_publicacion + timedelta(days=1)) if fecha_publicacion else None
        return f_ap, None, None

    texto_lower = texto_crudo.lower()
    fecha_apertura: Optional[date] = None
    fecha_cierre: Optional[date] = None
    plazo_texto: Optional[str] = None

    # 1. Fecha de apertura: Habitualmente el día siguiente al de la publicación en boletín
    if "día siguiente" in texto_lower or "dia siguiente" in texto_lower:
        if fecha_publicacion:
            fecha_apertura = fecha_publicacion + timedelta(days=1)
            plazo_texto = "El día siguiente al de la publicación oficial"
    else:
        # Buscar patrón explícito: a partir del DD de [mes] de AAAA
        match_ap = re.search(r"a\s+partir\s+del\s+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", texto_lower)
        if match_ap:
            d, m_str, y = int(match_ap.group(1)), match_ap.group(2), int(match_ap.group(3))
            m = MESES.get(m_str, 1)
            try:
                fecha_apertura = date(y, m, d)
            except ValueError:
                pass

    if not fecha_apertura and fecha_publicacion:
        fecha_apertura = fecha_publicacion + timedelta(days=1)

    # 2. Fecha de cierre: Detectar 'hasta el DD de [mes] de AAAA' o 'finalizará el DD/MM/AAAA'
    match_cierre = re.search(
        r"(?:hasta|finalizar[aá]|l[ií]mite)\s+(?:el\s+)?(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})",
        texto_lower,
    )
    if match_cierre:
        d, m_str, y = int(match_cierre.group(1)), match_cierre.group(2), int(match_cierre.group(3))
        m = MESES.get(m_str, 1)
        try:
            fecha_cierre = date(y, m, d)
        except ValueError:
            pass
    else:
        # Buscar también patrón con formato DD/MM/AAAA o DD-MM-AAAA
        match_cierre_fmt = re.search(
            r"(?:hasta|finalizar[aá]|l[ií]mite)\s+(?:el\s+)?(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
            texto_lower,
        )
        if match_cierre_fmt:
            d, m, y = int(match_cierre_fmt.group(1)), int(match_cierre_fmt.group(2)), int(match_cierre_fmt.group(3))
            try:
                fecha_cierre = date(y, m, d)
            except ValueError:
                pass
        else:
            # Detectar patrón de plazo relativo: 'plazo de un mes' / 'plazo de 30 días'
            if "un mes" in texto_lower:
                if fecha_apertura:
                    fecha_cierre = fecha_apertura + timedelta(days=30)
                    plazo_texto = plazo_texto or "1 mes a contar desde la apertura del plazo"
            elif "dos meses" in texto_lower:
                if fecha_apertura:
                    fecha_cierre = fecha_apertura + timedelta(days=60)
                    plazo_texto = plazo_texto or "2 meses a contar desde la apertura del plazo"

    return fecha_apertura, fecha_cierre, plazo_texto
