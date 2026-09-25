import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from ai.classifier import AIClassifierService
from ai.schemas import ConvocatoriaEnrichedClassification
from db.enums import DestinoGasto, EstadoConvocatoria, SectorVertical, Territorio, TipoAyuda
from db.models import Convocatoria
from main import cli


class TestAIClassifier(unittest.TestCase):

    def test_schema_json_validation(self):
        sample_json = """{
            "es_empresa_privada": true,
            "resumen_ejecutivo": "Subvención para digitalización e innovación en pymes industriales.",
            "territorio": "bizkaia",
            "sector_vertical": "industrial_mecanizado",
            "destino_gasto": "digitalizacion_software",
            "tipo_ayuda": "fondo_perdido",
            "intensidad_financiacion": 70.0,
            "presupuesto_total": 500000.0,
            "cuantia_maxima_solicitud": 30000.0,
            "beneficiarios_detalle": "Pymes y autónomos del sector industrial.",
            "requisitos_principales": ["Tener sede en Bizkaia", "Plantilla menor de 250 empleados"],
            "gastos_subvencionables": ["Adquisición de software ERP/CRM", "Consultoría"],
            "tags": ["pyme", "digitalizacion", "bizkaia"],
            "plazo_solicitud_texto": "1 mes desde la publicación en el BOB",
            "fecha_cierre": "2026-10-31",
            "score_relevancia": 0.95,
            "score_justificacion": "Alta oportunidad para empresas del sector industrial en Bizkaia."
        }"""

        obj = ConvocatoriaEnrichedClassification.model_validate_json(sample_json)
        self.assertTrue(obj.es_empresa_privada)
        self.assertEqual(obj.territorio, Territorio.bizkaia)
        self.assertEqual(obj.sector_vertical, SectorVertical.industrial_mecanizado)
        self.assertEqual(obj.destino_gasto, DestinoGasto.digitalizacion_software)
        self.assertEqual(obj.tipo_ayuda, TipoAyuda.fondo_perdido)
        self.assertEqual(obj.presupuesto_total, 500000.0)
        self.assertEqual(obj.cuantia_maxima_solicitud, 30000.0)
        self.assertEqual(obj.fecha_cierre, date(2026, 10, 31))
        self.assertEqual(obj.score_relevancia, 0.95)

    @patch("ai.classifier.httpx.Client")
    def test_classify_text_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200

        payload_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "es_empresa_privada": True,
                            "resumen_ejecutivo": "Ayuda para proyectos de I+D en Euskadi.",
                            "territorio": "euskadi_autonomica",
                            "sector_vertical": "tic_digitalizacion",
                            "destino_gasto": "i_mas_d_innovacion",
                            "tipo_ayuda": "fondo_perdido",
                            "intensidad_financiacion": 50.0,
                            "presupuesto_total": 1000000.0,
                            "cuantia_maxima_solicitud": 50000.0,
                            "beneficiarios_detalle": "Empresas con centro en Euskadi.",
                            "requisitos_principales": ["Proyecto innovador"],
                            "gastos_subvencionables": ["Personal I+D"],
                            "tags": ["innovacion", "spri"],
                            "plazo_solicitud_texto": "Hasta agotar fondos",
                            "fecha_cierre": None,
                            "score_relevancia": 0.9,
                            "score_justificacion": "Programa de alto interés para empresas tecnológicas."
                        })
                    }
                }
            ]
        }
        mock_response.json.return_value = payload_response
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        service = AIClassifierService(api_key="test_key")
        result = service.classify_text(
            titulo="ORDEN de ayudas a I+D",
            organismo="DEPARTAMENTO DE INDUSTRIA",
            texto_crudo="Texto completo de la resolución...",
        )

        self.assertTrue(result.es_empresa_privada)
        self.assertEqual(result.territorio, Territorio.euskadi_autonomica)
        self.assertEqual(result.score_relevancia, 0.9)

    @patch("ai.classifier.httpx.Client")
    def test_classify_text_retry_on_429(self, mock_client_cls):
        mock_client = MagicMock()

        resp_429 = MagicMock()
        resp_429.status_code = 429

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "es_empresa_privada": False,
                            "resumen_ejecutivo": "Oposición para puestos de funcionario.",
                            "beneficiarios_detalle": "Personas físicas individuales.",
                            "requisitos_principales": [],
                            "gastos_subvencionables": [],
                            "tags": ["oposicion"],
                            "score_relevancia": 0.0,
                            "score_justificacion": "Es empleo público, no aplica a empresas."
                        })
                    }
                }
            ]
        }

        mock_client.post.side_effect = [resp_429, resp_200]
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with patch("time.sleep", return_value=None):
            service = AIClassifierService(api_key="test_key", max_retries=3)
            result = service.classify_text("Convocatoria oposiciones", "Departamento", "Texto")
            self.assertFalse(result.es_empresa_privada)
            self.assertEqual(result.score_relevancia, 0.0)

    @patch("ai.classifier.AIClassifierService.classify_text")
    def test_process_convocatoria_classified(self, mock_classify_text):
        mock_classify_text.return_value = ConvocatoriaEnrichedClassification(
            es_empresa_privada=True,
            resumen_ejecutivo="Resumen ejecutivo pyme.",
            territorio=Territorio.gipuzkoa,
            sector_vertical=SectorVertical.multisectorial,
            destino_gasto=DestinoGasto.eficiencia_energia,
            tipo_ayuda=TipoAyuda.fondo_perdido,
            intensidad_financiacion=60.0,
            presupuesto_total=250000.0,
            cuantia_maxima_solicitud=15000.0,
            beneficiarios_detalle="Autónomos y pymes.",
            requisitos_principales=["Requisito 1"],
            gastos_subvencionables=["Gasto 1"],
            tags=["eficiencia"],
            plazo_solicitud_texto="30 días",
            fecha_cierre=None,
            score_relevancia=0.85,
            score_justificacion="Buena oportunidad de ahorro energético."
        )

        mock_db = MagicMock()
        conv = Convocatoria(
            id=1,
            id_origen="BOPV-2026-001",
            titulo="Subvención eficiencia energética",
            organismo="Organismo",
            url_oficial="https://example.com",
            texto_crudo="Texto de prueba...",
            estado=EstadoConvocatoria.INGESTADA,
        )

        service = AIClassifierService(api_key="test")
        updated = service.process_convocatoria(mock_db, conv)

        self.assertEqual(updated.estado, EstadoConvocatoria.CLASIFICADA)
        self.assertEqual(updated.resumen_ejecutivo, "Resumen ejecutivo pyme.")
        self.assertEqual(updated.territorio, Territorio.gipuzkoa)
        self.assertEqual(updated.score_relevancia, 0.85)
        mock_db.commit.assert_called_once()

    def test_cli_classify_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--limit", result.output)
        self.assertIn("--force", result.output)


if __name__ == "__main__":
    unittest.main()
