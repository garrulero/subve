import unittest
from datetime import date
from unittest.mock import MagicMock, patch
import httpx
from typer.testing import CliRunner

from main import cli
from db.enums import EstadoConvocatoria
from scrapers.bopv import BOPVScraper, get_last_n_working_days


class TestBOPVScraper(unittest.TestCase):

    def test_get_last_n_working_days_friday(self):
        # 2026-09-25 es viernes
        friday = date(2026, 9, 25)
        days = get_last_n_working_days(1, reference_date=friday)
        self.assertEqual(days, [friday])

        days_5 = get_last_n_working_days(5, reference_date=friday)
        self.assertEqual(len(days_5), 5)
        expected_5 = [
            date(2026, 9, 25), # Viernes
            date(2026, 9, 24), # Jueves
            date(2026, 9, 23), # Miércoles
            date(2026, 9, 22), # Martes
            date(2026, 9, 21), # Lunes
        ]
        self.assertEqual(days_5, expected_5)

    def test_get_last_n_working_days_saturday(self):
        # 2026-09-26 es sábado
        saturday = date(2026, 9, 26)
        days = get_last_n_working_days(3, reference_date=saturday)
        expected_3 = [
            date(2026, 9, 25), # Viernes
            date(2026, 9, 24), # Jueves
            date(2026, 9, 23), # Miércoles
        ]
        self.assertEqual(days, expected_3)

    def test_get_last_n_working_days_30(self):
        friday = date(2026, 9, 25)
        days_30 = get_last_n_working_days(30, reference_date=friday)
        self.assertEqual(len(days_30), 30)
        # Ningún día debe ser sábado (5) ni domingo (6)
        for d in days_30:
            self.assertLess(d.weekday(), 5)

    @patch("scrapers.bopv.httpx.Client")
    def test_bopv_scraper_single_day(self, mock_client_cls):
        xml_content = """<?xml version="1.0" encoding="ISO-8859-1"?>
        <rss version="2.0">
            <channel>
                <pubDate>2026-09-25</pubDate>
                <item>
                    <title>ORDEN de ayuda y subvencion a pymes para innovacion</title>
                    <link>https://www.euskadi.eus/bopv2/datos/2026/09/2604010a.shtml</link>
                    <guid>https://www.euskadi.eus/bopv2/datos/2026/09/2604010a.shtml</guid>
                </item>
            </channel>
        </rss>"""

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = xml_content.encode("iso-8859-1")
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        scraper = BOPVScraper(days=1)
        items = scraper.fetch_items()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id_origen"], "BOPV-2604010a")
        self.assertEqual(items[0]["pub_date_str"], "2026-09-25")

        # Filtrar y enriquecer
        relevant = scraper.filter_relevant(items)
        self.assertEqual(len(relevant), 1)

        enriched = scraper.enrich_item(relevant[0])
        self.assertEqual(enriched["estado"], EstadoConvocatoria.INGESTADA)

    @patch("scrapers.bopv.httpx.Client")
    def test_bopv_scraper_multiple_days_with_404(self, mock_client_cls):
        mock_client = MagicMock()

        def side_effect_get(url, *args, **kwargs):
            mock_resp = MagicMock()
            if "20260925" in url or "Ultimo.xml" in url:
                mock_resp.status_code = 200
                xml = """<?xml version="1.0"?><rss><channel><item>
                <title>Subvencion para desarrollo</title>
                <link>https://www.euskadi.eus/bopv2/datos/2026/09/2604010a.shtml</link>
                </item></channel></rss>"""
                mock_resp.content = xml.encode("utf-8")
                return mock_resp
            else:
                # Simular 404 en fin de semana / festivo / día sin publicación
                request = httpx.Request("GET", url)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError("Not Found", request=request, response=response)

        mock_client.get.side_effect = side_effect_get
        mock_client_cls.return_value.__enter__.return_value = mock_client

        scraper = BOPVScraper(days=3)
        # No debe lanzar excepción por los 404
        items = scraper.fetch_items()
        self.assertGreaterEqual(len(items), 1)

    def test_cli_bopv_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scrape", "bopv", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--days", result.output)


if __name__ == "__main__":
    unittest.main()
