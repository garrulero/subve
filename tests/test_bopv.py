import unittest
from unittest.mock import MagicMock, patch
import httpx
from typer.testing import CliRunner

from main import cli
from db.enums import EstadoConvocatoria
from scrapers.bopv import BOPVScraper


class TestBOPVScraper(unittest.TestCase):

    @patch("scrapers.bopv.httpx.Client")
    def test_get_latest_bulletin_info(self, mock_client_cls):
        xml_content = """<?xml version="1.0" encoding="ISO-8859-1"?>
        <rss version="2.0">
            <channel>
                <title>Boletín Nº 184, fecha 25/09/2026</title>
                <pubDate>2026-09-24</pubDate>
            </channel>
        </rss>"""

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = xml_content.encode("iso-8859-1")
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        scraper = BOPVScraper(days=1)
        latest_info = scraper._get_latest_bulletin_info(mock_client)

        self.assertIsNotNone(latest_info)
        num, date_str, year, month = latest_info
        self.assertEqual(num, 184)
        self.assertEqual(date_str, "2026-09-25")
        self.assertEqual(year, 2026)
        self.assertEqual(month, 9)

    @patch("scrapers.bopv.httpx.Client")
    def test_fetch_items_multiple_days(self, mock_client_cls):
        mock_client = MagicMock()

        def side_effect_get(url_arg, *args, **kwargs):
            url_str = str(url_arg)
            mock_resp = MagicMock()
            if "Ultimo.xml" in url_str:
                mock_resp.status_code = 200
                xml = """<?xml version="1.0"?><rss><channel>
                <title>Boletín Nº 184, fecha 25/09/2026</title>
                </channel></rss>"""
                mock_resp.content = xml.encode("utf-8")
                return mock_resp
            elif "s26_0184.shtml" in url_str:
                mock_resp.status_code = 200
                html = """<html><body>
                <h1>Sumario n.º 184, viernes 25 de septiembre de 2026</h1>
                <h2>DEPARTAMENTO DE HACIENDA Y FINANZAS</h2>
                <a href="2604010a.shtml">RESOLUCIÓN de ayuda y subvencion a pymes</a>
                </body></html>"""
                mock_resp.text = html
                return mock_resp
            elif "s26_0183.shtml" in url_str:
                mock_resp.status_code = 200
                html = """<html><body>
                <h1>Sumario n.º 183, jueves 24 de septiembre de 2026</h1>
                <h2>DEPARTAMENTO DE DESARROLLO ECONÓMICO</h2>
                <a href="2603990a.shtml">ORDEN de beca y programa de apoyo</a>
                </body></html>"""
                mock_resp.text = html
                return mock_resp
            else:
                req = httpx.Request("GET", url_str)
                resp = httpx.Response(404, request=req)
                raise httpx.HTTPStatusError("Not Found", request=req, response=resp)

        mock_client.get.side_effect = side_effect_get
        mock_client_cls.return_value.__enter__.return_value = mock_client

        scraper = BOPVScraper(days=2)
        items = scraper.fetch_items()

        self.assertEqual(len(items), 2)
        ids = [it["id_origen"] for it in items]
        self.assertIn("BOPV-2604010a", ids)
        self.assertIn("BOPV-2603990a", ids)

        # Filtrar e ingestar
        relevant = scraper.filter_relevant(items)
        self.assertEqual(len(relevant), 2)

        enriched = scraper.enrich_item(relevant[0])
        self.assertEqual(enriched["estado"], EstadoConvocatoria.INGESTADA)

    def test_cli_bopv_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scrape", "bopv", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--days", result.output)


if __name__ == "__main__":
    unittest.main()
