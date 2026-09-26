import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from ai.classifier import AIClassifierService
from ai.schemas import ConvocatoriaEnrichedClassification
from db.enums import (
    DestinoGasto,
    EstadoConvocatoria,
    PerfilDestinatario,
    SectorVertical,
    Territorio,
    TipoAyuda,
    TipoDocumento,
)
from db.models import Convocatoria
from main import cli


class TestAIClassifier(unittest.TestCase):

    def test_schema_json_validation(self):
        sample_json = """{
            "tipo_documento": "subvencion_ayuda",
            "perfil_destinatario": "empresa_pyme",
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
        self.assertEqual(obj.tipo_documento, TipoDocumento.subvencion_ayuda)
        self.assertEqual(obj.perfil_destinatario, PerfilDestinatario.empresa_pyme)
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
            "answers": {
                "tipo_documento": {"choice": "subvencion_ayuda", "confidence": 0.95},
                "perfil_destinatario": {"choice": "empresa_pyme", "confidence": 0.9},
                "territorio": {"choice": "euskadi_autonomica", "confidence": 0.85},
                "sector_vertical": {"choice": "tic_digitalizacion", "confidence": 0.8},
                "destino_gasto": {"choice": "i_mas_d_innovacion", "confidence": 0.9},
                "tipo_ayuda": {"choice": "fondo_perdido", "confidence": 0.95},
            }
        }
        mock_response.json.return_value = payload_response
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        service = AIClassifierService(api_key="test_key")
        result = service.classify_convocatoria_raw(
            titulo="ORDEN de ayudas a I+D",
            organismo="DEPARTAMENTO DE INDUSTRIA",
            texto_crudo="Texto completo de la resolución...",
        )

        self.assertEqual(result["tipo_documento"]["choice"], "subvencion_ayuda")
        self.assertEqual(result["perfil_destinatario"]["choice"], "empresa_pyme")

    @patch("ai.classifier.httpx.Client")
    def test_classify_text_retry_on_429(self, mock_client_cls):
        mock_client = MagicMock()

        resp_429 = MagicMock()
        resp_429.status_code = 429

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "answers": {
                "tipo_documento": {"choice": "empleo_publico", "confidence": 0.95},
                "perfil_destinatario": {"choice": "administracion_publica", "confidence": 0.9},
            }
        }

        mock_client.post.side_effect = [resp_429, resp_200]
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with patch("time.sleep", return_value=None):
            service = AIClassifierService(api_key="test_key", max_retries=3)
            result = service.classify_convocatoria_raw("Convocatoria oposiciones", "Departamento", "Texto")
            self.assertEqual(result["tipo_documento"]["choice"], "empleo_publico")

    @patch("ai.classifier.AIClassifierService.classify_convocatoria_raw")
    def test_process_convocatoria_classified(self, mock_classify_raw):
        mock_classify_raw.return_value = {
            "tipo_documento": {"choice": "subvencion_ayuda", "confidence": 0.95},
            "perfil_destinatario": {"choice": "empresa_pyme", "confidence": 0.85},
            "territorio": {"choice": "gipuzkoa", "confidence": 0.9},
            "sector_vertical": {"choice": "multisectorial", "confidence": 0.8},
            "destino_gasto": {"choice": "eficiencia_energia", "confidence": 0.9},
            "tipo_ayuda": {"choice": "fondo_perdido", "confidence": 0.95},
        }

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
        self.assertEqual(updated.tipo_documento, TipoDocumento.subvencion_ayuda)
        self.assertEqual(updated.perfil_destinatario, PerfilDestinatario.empresa_pyme)
        self.assertEqual(updated.territorio, Territorio.gipuzkoa)
        self.assertEqual(updated.score_relevancia, 0.85)
        mock_db.commit.assert_called_once()

    @patch("ai.classifier.AIClassifierService.classify_convocatoria_raw")
    def test_process_convocatoria_discapacidad_tercer_sector(self, mock_classify_raw):
        mock_classify_raw.return_value = {
            "tipo_documento": {"choice": "subvencion_ayuda", "confidence": 0.9},
            "perfil_destinatario": {"choice": "discapacidad_dependencia", "confidence": 0.9},
            "territorio": {"choice": "bizkaia", "confidence": 0.95},
            "sector_vertical": {"choice": "multisectorial", "confidence": 0.8},
            "destino_gasto": {"choice": "asistencia_accesibilidad_social", "confidence": 0.9},
            "tipo_ayuda": {"choice": "fondo_perdido", "confidence": 0.95},
        }

        mock_db = MagicMock()
        conv = Convocatoria(
            id=2,
            id_origen="BOB-2026-002",
            titulo="Subvención accesibilidad y discapacidad",
            organismo="Diputación Foral de Bizkaia",
            url_oficial="https://example.com/bob",
            texto_crudo="Texto accesibilidad...",
            estado=EstadoConvocatoria.INGESTADA,
        )

        service = AIClassifierService(api_key="test")
        updated = service.process_convocatoria(mock_db, conv)

        self.assertEqual(updated.estado, EstadoConvocatoria.CLASIFICADA)
        self.assertEqual(updated.tipo_documento, TipoDocumento.subvencion_ayuda)
        self.assertEqual(updated.perfil_destinatario, PerfilDestinatario.discapacidad_dependencia)
        self.assertEqual(updated.destino_gasto, DestinoGasto.asistencia_accesibilidad_social)
        self.assertFalse(updated.es_empresa_privada)
        mock_db.commit.assert_called_once()

    def test_process_batch_includes_error_state(self):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        service = AIClassifierService(api_key="test")
        service.process_batch(mock_db, force=False)

        mock_query.filter.assert_called_once()
        filter_arg = mock_query.filter.call_args[0][0]
        self.assertIsNotNone(filter_arg)

    def test_cli_classify_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["classify", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--limit", result.output)
        self.assertIn("--force", result.output)


if __name__ == "__main__":
    unittest.main()
