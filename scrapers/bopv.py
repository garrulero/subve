import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from db.enums import EstadoConvocatoria
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Palabras clave prioritarias para ayudas, subvenciones e incentivos a empresas, particulares y tercer sector
KEYWORDS_RELEVANTES = [
    "subvenci",
    "ayuda",
    "beca",
    "bono",
    "incentivo",
    "financiaci",
    "programa de apoyo",
    "innovaci",
    "digitaliza",
    "moderniza",
    "competitividad",
    "pyme",
    "emprend",
    "fomento",
    "promoci",
    "fondo",
    "reindustrializa",
    "convocatoria",
    "crédito",
    "credito",
    "programa",
    # Términos sociales, particulares y discapacidad:
    "discapacidad",
    "dependencia",
    "inclusi",
    "accesibil",
    "social",
    "tercer sector",
    "asociaci",
    "vivienda",
    "familia",
    "conciliaci",
    "vulnerable",
]

# Patrones típicos de anuncios que NO son subvenciones empresariales (empleo público, sanciones, etc.)
PATRONES_EXCLUSION = [
    r"puesto de trabajo",
    r"libre designaci[oó]n",
    r"personal funcionario",
    r"bolsa de trabajo",
    r"tribunal calificador",
    r"nombramiento",
    r"cese de",
    r"jubilaci[oó]n",
    r"notificaci[oó]n de sanci[oó]n",
    r"aprovechamiento de aguas",
]

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


class BOPVScraper(BaseScraper):
    """
    Scraper oficial para el Boletín Oficial del País Vasco (BOPV).
    Detecta el boletín actual desde Ultimo.xml e itera hacia atrás por número correlativo
    descargando los sumarios HTML históricos (sYY_NNNN.shtml).
    """

    DEFAULT_SUMARIO_URL = "https://www.euskadi.eus/bopv2/datos/Ultimo.xml"
    BASE_DATOS_URL = "https://www.euskadi.eus/web01-bopv/es/bopv2/datos"

    def __init__(
        self,
        sumario_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
        days: int = 1,
    ) -> None:
        super().__init__(name="BOPVScraper", source_id="BOPV")
        self.sumario_url = sumario_url
        self.timeout_seconds = timeout_seconds
        self.days = max(1, days)
        self.client_headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; SubvencionesEuskadiBot/1.0; "
                "+https://github.com/subvenciones-core)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def fetch_items(self) -> List[Dict[str, Any]]:
        """
        Descarga el/los sumario(s) del BOPV.
        Si self.sumario_url está definido, descarga esa URL directamente.
        En caso contrario, detecta el boletín actual desde Ultimo.xml e itera
        hacia atrás los últimos N boletines.
        """
        items: List[Dict[str, Any]] = []
        seen_ids = set()

        with httpx.Client(
            timeout=self.timeout_seconds,
            headers=self.client_headers,
            follow_redirects=True,
        ) as client:
            if self.sumario_url:
                logger.info(f"[{self.name}] Descargando sumario específico desde {self.sumario_url}")
                return self._fetch_url_xml_items(client, self.sumario_url)

            # 1. Detección del boletín inicial desde Ultimo.xml
            latest_info = self._get_latest_bulletin_info(client)
            if not latest_info:
                logger.error(f"[{self.name}] No se pudo detectar la información del boletín inicial desde Ultimo.xml")
                return []

            latest_num, latest_date_str, latest_year, latest_month = latest_info
            logger.info(
                f"[{self.name}] Boletín inicial detectado: Nº {latest_num} "
                f"({latest_date_str}, año={latest_year}, mes={latest_month:02d})"
            )

            # 2. Iteración hacia atrás para N boletines
            current_year = latest_year
            current_month = latest_month

            for i in range(self.days):
                bulletin_num = latest_num - i
                if bulletin_num <= 0:
                    break

                bulletin_items, current_year, current_month = self._fetch_bulletin_by_number(
                    client, bulletin_num, current_year, current_month
                )

                # Aplicar filtrado de relevancia para logging informativo
                relevant_in_bulletin = self.filter_relevant(bulletin_items)
                logger.info(
                    f"[{self.name}] Boletín Nº {bulletin_num} ({current_year}/{current_month:02d}): "
                    f"{len(bulletin_items)} anuncios encontrados, {len(relevant_in_bulletin)} pasaron el filtro de subvenciones."
                )

                for item in bulletin_items:
                    if item["id_origen"] not in seen_ids:
                        seen_ids.add(item["id_origen"])
                        items.append(item)

        return items

    def _get_latest_bulletin_info(self, client: httpx.Client) -> Optional[Tuple[int, str, int, int]]:
        """
        Descarga Ultimo.xml y extrae (bulletin_number, date_str, year, month).
        """
        try:
            r = client.get(self.DEFAULT_SUMARIO_URL)
            r.raise_for_status()
            content = r.content
            try:
                xml_text = content.decode("utf-8")
            except UnicodeDecodeError:
                xml_text = content.decode("iso-8859-1", errors="replace")

            root = ET.fromstring(xml_text)
            channel_title = root.findtext(".//channel/title") or ""
            channel_pubdate = root.findtext(".//channel/pubDate") or ""

            match_num = re.search(r"N[ºo\.\s]*(\d+)", channel_title, re.IGNORECASE)
            match_date = re.search(r"fecha\s*(\d{2}/\d{2}/\d{4})", channel_title, re.IGNORECASE)

            if not match_num:
                return None

            bulletin_num = int(match_num.group(1))
            date_str = match_date.group(1) if match_date else None

            if date_str:
                dt = datetime.strptime(date_str, "%d/%m/%Y").date()
                pub_date_formatted = dt.strftime("%Y-%m-%d")
                year, month = dt.year, dt.month
            elif channel_pubdate and len(channel_pubdate) >= 10:
                dt = datetime.strptime(channel_pubdate[:10], "%Y-%m-%d").date()
                pub_date_formatted = dt.strftime("%Y-%m-%d")
                year, month = dt.year, dt.month
            else:
                dt = date.today()
                pub_date_formatted = dt.strftime("%Y-%m-%d")
                year, month = dt.year, dt.month

            return bulletin_num, pub_date_formatted, year, month
        except Exception as ex:
            logger.error(f"[{self.name}] Error descargando Ultimo.xml: {ex}")
            return None

    def _fetch_bulletin_by_number(
        self,
        client: httpx.Client,
        bulletin_num: int,
        year: int,
        month: int,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """
        Descarga el sumario HTML para un número correlativo de boletín.
        Maneja retroceso de mes (MM - 1) si devuelve 404.
        Retorna (items, updated_year, updated_month).
        """
        yy = str(year)[2:]
        filename = f"s{yy}_{bulletin_num:04d}.shtml"

        # Candidatos de (año, mes) a probar en caso de cambio de mes o año
        candidate_dates = [(year, month)]

        # Agregar mes anterior
        prev_m = month - 1
        prev_y = year
        if prev_m < 1:
            prev_m = 12
            prev_y = year - 1
        candidate_dates.append((prev_y, prev_m))

        # Agregar dos meses atrás por si acaso
        prev_m2 = prev_m - 1
        prev_y2 = prev_y
        if prev_m2 < 1:
            prev_m2 = 12
            prev_y2 = prev_y - 1
        candidate_dates.append((prev_y2, prev_m2))

        for y, m in candidate_dates:
            url = f"{self.BASE_DATOS_URL}/{y}/{m:02d}/{filename}"
            try:
                r = client.get(url)
                if r.status_code == 200:
                    items = self._parse_html_sumario(r.text, url, y, m, bulletin_num)
                    return items, y, m
                elif r.status_code == 404:
                    continue
                else:
                    logger.warning(f"[{self.name}] Código HTTP {r.status_code} al consultar {url}")
            except Exception as ex:
                logger.warning(f"[{self.name}] Error al consultar {url}: {ex}")

        logger.info(f"[{self.name}] Boletín Nº {bulletin_num} ({filename}) no encontrado (HTTP 404).")
        return [], year, month

    def _parse_html_sumario(
        self,
        html_text: str,
        sumario_url: str,
        year: int,
        month: int,
        bulletin_num: int,
    ) -> List[Dict[str, Any]]:
        """
        Parsea el sumario HTML del boletín sYY_NNNN.shtml y extrae los elementos.
        """
        soup = BeautifulSoup(html_text, "html.parser")
        items: List[Dict[str, Any]] = []

        # Intentar extraer fecha exacta del encabezado del sumario HTML
        pub_date_str = f"{year:04d}-{month:02d}-01"
        header_text = soup.get_text()
        date_match = re.search(
            r"Sumario\s+n\.[ºo]?\s*\d+.*?,.*?\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})",
            header_text,
            re.IGNORECASE,
        )
        if date_match:
            d_day = int(date_match.group(1))
            m_str = date_match.group(2).lower()
            d_year = int(date_match.group(3))
            d_month = MESES_ES.get(m_str, month)
            pub_date_str = f"{d_year:04d}-{d_month:02d}-{d_day:02d}"

        # Extraer enlaces a las disposiciones
        for a in soup.find_all("a", href=True):
            href = a["href"]
            match = re.search(r"(\d{6,8}[a-z]?)\.shtml", href, re.IGNORECASE)
            if not match:
                continue

            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            code = match.group(1).lower()
            id_origen = f"BOPV-{code}"

            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = f"https://www.euskadi.eus{href}"
            else:
                full_url = f"{self.BASE_DATOS_URL}/{year}/{month:02d}/{href}"

            # Extraer organismo emisor / departamento
            organismo = None
            curr = a.parent
            while curr and not organismo:
                prev = curr.find_previous_sibling()
                while prev and not organismo:
                    txt = prev.get_text(strip=True)
                    if txt and any(k in txt.upper() for k in ["DEPARTAMENTO", "OSAKIDETZA", "AGENCIA", "AUTORIDAD", "CONSEJERIA", "DIPUTACIÓN"]):
                        organismo = txt
                        break
                    prev = prev.previous_sibling
                curr = curr.parent

            items.append({
                "id_origen": id_origen,
                "title": title,
                "link": full_url,
                "guid": full_url,
                "organismo": organismo,
                "pub_date_str": pub_date_str,
            })

        return items

    def _fetch_url_xml_items(
        self,
        client: httpx.Client,
        url: str,
    ) -> List[Dict[str, Any]]:
        """Fallback para URLs XML directas especificadas manualmente."""
        r = client.get(url)
        r.raise_for_status()
        content = r.content
        try:
            xml_text = content.decode("iso-8859-1")
        except UnicodeDecodeError:
            xml_text = content.decode("utf-8", errors="replace")

        root = ET.fromstring(xml_text)
        channel_pub_date = (root.findtext(".//channel/pubDate") or "").strip()
        xml_items = root.findall(".//item")
        items: List[Dict[str, Any]] = []

        for item in xml_items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            pub_date_str = (item.findtext("pubDate") or channel_pub_date or "").strip()

            if not link and not title:
                continue

            id_origen = self._extract_id_origen(guid or link)
            items.append({
                "id_origen": id_origen,
                "title": title,
                "link": link,
                "guid": guid,
                "pub_date_str": pub_date_str,
            })

        return items

    def _extract_id_origen(self, identifier: str) -> str:
        """
        Normaliza el ID unívoco a partir del nombre del fichero o hash canónico.
        Ejemplo: https://www.euskadi.eus/y22-bopv/es/bopv2/datos/2026/09/2604010a.shtml -> BOPV-2604010a
        """
        match = re.search(r"(\d{6,8}[a-z]?)\.s?html?", identifier, re.IGNORECASE)
        if match:
            return f"BOPV-{match.group(1).lower()}"
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", identifier)
        return f"BOPV-{clean_id[-40:]}"

    def filter_relevant(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filtra los elementos del sumario evaluando palabras clave de subvenciones
        y descartando convocatorias internas de empleo público.
        """
        relevant: List[Dict[str, Any]] = []

        for item in items:
            title_lower = item["title"].lower()

            # Comprobar si coincide con palabras clave relevantes
            has_relevant_kw = any(kw in title_lower for kw in KEYWORDS_RELEVANTES)

            # Comprobar si es un falso positivo típico de empleo público
            has_exclusion = any(re.search(pat, title_lower) for pat in PATRONES_EXCLUSION)

            # Si contiene palabra clave y no cae en exclusión evidente
            if has_relevant_kw and not has_exclusion:
                relevant.append(item)
            elif "subvenci" in title_lower or "ayuda" in title_lower or "beca" in title_lower:
                # Si menciona explícitamente subvención, ayuda o beca, siempre se conserva
                relevant.append(item)

        return relevant

    def enrich_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Descarga la página completa del anuncio oficial para extraer el texto íntegro
        y metadatos como el organismo emisor.
        """
        url = item["link"]
        texto_crudo: Optional[str] = None
        organismo: Optional[str] = item.get("organismo")
        fecha_publicacion: Optional[date] = None

        # Parsear fecha de publicación si está disponible
        if item.get("pub_date_str"):
            try:
                fecha_publicacion = datetime.strptime(
                    item["pub_date_str"][:10], "%Y-%m-%d"
                ).date()
            except ValueError:
                fecha_publicacion = date.today()
        else:
            fecha_publicacion = date.today()

        if url:
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    headers=self.client_headers,
                    follow_redirects=True,
                ) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        try:
                            html_text = resp.content.decode("iso-8859-1")
                        except UnicodeDecodeError:
                            html_text = resp.content.decode("utf-8", errors="replace")

                        soup = BeautifulSoup(html_text, "html.parser")

                        # Intentar extraer organismo de metadatos si no se obtuvo en el sumario
                        if not organismo:
                            meta_creator = soup.find("meta", attrs={"name": re.compile(r"dc\.creator", re.I)})
                            if meta_creator and meta_creator.get("content"):
                                organismo = str(meta_creator["content"])[:255]

                        # Extraer contenido principal (<main> o contenedor de texto)
                        main_tag = soup.find("main") or soup.find("div", class_=re.compile(r"cuerpo|content|edukiontzia", re.I))
                        if main_tag:
                            for s in main_tag(["script", "style", "nav", "header", "footer"]):
                                s.decompose()
                            texto_crudo = main_tag.get_text(separator="\n", strip=True)
                        else:
                            body = soup.find("body")
                            if body:
                                for s in body(["script", "style", "nav", "header", "footer"]):
                                    s.decompose()
                                texto_crudo = body.get_text(separator="\n", strip=True)

            except Exception as ex:
                logger.warning(
                    f"[{self.name}] No se pudo descargar el detalle completo de {url}: {ex}"
                )

        # Si no se pudo obtener organismo, deducirlo del título si tiene estructura clásica
        if not organismo and " de la " in item["title"]:
            parts = item["title"].split(" de la ")
            if len(parts) > 1:
                organismo = ("de la " + parts[1].split(",")[0])[:255]

        return {
            "id_origen": item["id_origen"],
            "fuente": self.source_id,
            "titulo": item["title"],
            "organismo": organismo,
            "url_oficial": url,
            "texto_crudo": texto_crudo,
            "fecha_publicacion": fecha_publicacion,
            "estado": EstadoConvocatoria.INGESTADA,
        }


