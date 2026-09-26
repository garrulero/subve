-- ==============================================================================
-- SUBVENCIONES-CORE: Migración de Base de Datos (Fase 2)
-- Añade columnas enriquecidas para clasificación mediante IA
-- ==============================================================================

ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS resumen_ejecutivo TEXT;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS presupuesto_total DOUBLE PRECISION;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS cuantia_maxima_solicitud DOUBLE PRECISION;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS tipo_ayuda VARCHAR(50);
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS beneficiarios_detalle TEXT;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS requisitos_principales JSONB;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS gastos_subvencionables JSONB;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS tags JSONB;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS score_relevancia DOUBLE PRECISION;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS score_justificacion TEXT;
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS plazo_solicitud_texto VARCHAR(255);
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(50);
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS perfil_destinatario VARCHAR(50);
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);
ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS ai_processed_at TIMESTAMP WITH TIME ZONE;
