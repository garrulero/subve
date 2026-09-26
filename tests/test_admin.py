import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from db.base import get_db
from db.enums import EstadoConvocatoria, PerfilDestinatario, TipoDocumento
from db.models import Convocatoria


class TestAdminEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.mock_db = MagicMock()

        def override_get_db():
            yield self.mock_db

        app.dependency_overrides[get_db] = override_get_db

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_root_redirect_to_admin(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/admin")

    def test_admin_page_returns_html(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("SUBVE - Panel de Administración", response.text)

    def test_get_stats(self):
        self.mock_db.query().scalar.return_value = 10
        self.mock_db.query().group_by().all.return_value = []

        response = self.client.get("/api/admin/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_convocatorias", data)
        self.assertIn("estados", data)
        self.assertIn("perfiles", data)

    def test_get_convocatorias(self):
        self.mock_db.query().filter().count.return_value = 1
        dummy_conv = MagicMock(spec=Convocatoria)
        dummy_conv.id = 1
        dummy_conv.id_origen = "2026/01"
        dummy_conv.fuente = "bopv"
        dummy_conv.titulo = "Ayuda de prueba"
        dummy_conv.organismo = "Departamento de Industria"
        dummy_conv.url_oficial = "https://example.com"
        dummy_conv.texto_crudo = "Texto de ejemplo"
        dummy_conv.fecha_publicacion = None
        dummy_conv.estado = EstadoConvocatoria.INGESTADA
        dummy_conv.es_empresa_privada = True
        dummy_conv.tipo_documento = TipoDocumento.subvencion_ayuda
        dummy_conv.perfil_destinatario = PerfilDestinatario.empresa_pyme
        dummy_conv.territorio = None
        dummy_conv.sector_vertical = None
        dummy_conv.destino_gasto = None
        dummy_conv.tipo_ayuda = None
        dummy_conv.intensidad_financiacion = None
        dummy_conv.tamano_empresa = None
        dummy_conv.regimen_concesion = None
        dummy_conv.fecha_apertura = None
        dummy_conv.fecha_cierre = None
        dummy_conv.resumen_ejecutivo = "Resumen"
        dummy_conv.presupuesto_total = None
        dummy_conv.cuantia_maxima_solicitud = None
        dummy_conv.beneficiarios_detalle = None
        dummy_conv.requisitos_principales = None
        dummy_conv.gastos_subvencionables = None
        dummy_conv.tags = []
        dummy_conv.score_relevancia = 0.95
        dummy_conv.score_justificacion = "Justificación"
        dummy_conv.plazo_solicitud_texto = None
        dummy_conv.ai_model = "jev"
        dummy_conv.ai_processed_at = None
        dummy_conv.created_at = None
        dummy_conv.updated_at = None

        self.mock_db.query().order_by().offset().limit().all.return_value = [dummy_conv]

        response = self.client.get("/api/admin/convocatorias?search=Ayuda")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertIn("total", data)

    @patch("web.admin.BOPVScraper")
    def test_action_scrape(self, mock_scraper_cls):
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.run.return_value = {"total": 5, "inserted": 3, "skipped": 2}
        mock_scraper_cls.return_value = mock_scraper_instance

        response = self.client.post("/api/admin/actions/scrape", json={"days": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["stats"]["inserted"], 3)

    @patch("web.admin.AIClassifierService")
    def test_action_classify(self, mock_classifier_cls):
        mock_classifier_instance = MagicMock()
        mock_classifier_instance.process_batch.return_value = {
            "total": 3,
            "clasificadas": 2,
            "descartadas": 1,
            "errores": 0,
        }
        mock_classifier_cls.return_value = mock_classifier_instance

        response = self.client.post("/api/admin/actions/classify", json={"limit": 10, "force": False})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["stats"]["clasificadas"], 2)

    def test_get_logs(self):
        response = self.client.get("/api/admin/logs/app.log")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["log_name"], "app.log")
        self.assertIn("entries", data)


if __name__ == "__main__":
    unittest.main()
