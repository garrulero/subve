import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

from db.enums import EstadoConvocatoria
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Palabras clave prioritarias para ayudas, subvenciones e incentivos a empresas y cultura
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


class BOPVScraper(BaseScraper):
    """
    Scraper oficial para el Boletín Oficial del País Vasco (BOPV).
    Descarga el sumario diario estructurado en XML/RSS y extrae los anuncios
    relevantes para pymes, talleres y entidades culturales.
    """

    DEFAULT_SUMARIO_URL = "https://www.euskadi.eus/bopv2/datos/Ultimo.xml"

    def __init__(
        self,
        sumario_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(name="BOPVScraper", source_id="BOPV")
        self.sumario_url = sumario_url or self.DEFAULT_SUMARIO_URL
        self.timeout_seconds = timeout_seconds
        self.client_headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; SubvencionesEuskadiBot/1.0; "
                "+https://github.com/subvenciones-core)"
            ),
            "Accept": "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
        }

    def fetch_items(self) -> List[Dict[str, Any]]:
        """
        Descarga el sumario XML oficial del BOPV y parsea sus elementos <item>.
        """
        logger.info(f"[{self.name}] Descargando sumario desde {self.sumario_url}")
        items: List[Dict[str, Any]] = []

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers=self.client_headers,
                follow_redirects=True,
            ) as client:
                response = client.get(self.sumario_url)
                response.raise_for_status()

                # El BOPV suele codificar en ISO-8859-1 o UTF-8
                content = response.content
                try:
                    xml_text = content.decode("iso-8859-1")
                except UnicodeDecodeError:
                    xml_text = content.decode("utf-8", errors="replace")

                root = ET.fromstring(xml_text)
                xml_items = root.findall(".//item")

                for item in xml_items:
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    guid = (item.findtext("guid") or link).strip()
                    pub_date_str = (item.findtext("pubDate") or "").strip()

                    if not link and not title:
                        continue

                    # Extraer identificador único de la disposición a partir de la URL o GUID
                    id_origen = self._extract_id_origen(guid or link)

                    items.append({
                        "id_origen": id_origen,
                        "title": title,
                        "link": link,
                        "guid": guid,
                        "pub_date_str": pub_date_str,
                    })

        except httpx.HTTPError as http_err:
            logger.error(f"[{self.name}] Error HTTP al consultar el sumario: {http_err}")
            raise
        except ET.ParseError as parse_err:
            logger.error(f"[{self.name}] Error parseando XML del sumario: {parse_err}")
            raise
        except Exception as ex:
            logger.error(f"[{self.name}] Error inesperado en fetch_items: {ex}", exc_info=True)
            raise

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
            elif "subvenci" in title_lower or "ayuda" in title_lower:
                # Si menciona explícitamente subvención o ayuda, siempre se conserva
                relevant.append(item)

        return relevant

    def enrich_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Descarga la página completa del anuncio oficial para extraer el texto íntegro
        y metadatos como el organismo emisor.
        """
        url = item["link"]
        texto_crudo: Optional[str] = None
        organismo: Optional[str] = None
        fecha_publicacion: Optional[date] = None

        # Parsear fecha de publicación del sumario si está disponible
        if item.get("pub_date_str"):
            try:
                # Formato típico YYYY-MM-DD
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

                        # Intentar extraer organismo de metadatos o cabecera
                        meta_creator = soup.find("meta", attrs={"name": re.compile(r"dc\.creator", re.I)})
                        if meta_creator and meta_creator.get("content"):
                            organismo = str(meta_creator["content"])[:255]

                        # Extraer contenido principal (<main> o contenedor de texto)
                        main_tag = soup.find("main") or soup.find("div", class_=re.compile(r"cuerpo|content|edukiontzia", re.I))
                        if main_tag:
                            # Eliminar scripts y estilos
                            for s in main_tag(["script", "style", "nav", "header", "footer"]):
                                s.decompose()
                            texto_crudo = main_tag.get_text(separator="\n", strip=True)
                        else:
                            # Fallback: texto del body completo
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
