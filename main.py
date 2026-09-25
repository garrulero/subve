import hashlib
import logging
import sys
from contextlib import asynccontextmanager
from typing import List, Optional

import typer
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config.settings import settings
from db.base import SessionLocal, get_db, init_database
from db.enums import EstadoConvocatoria
from db.models import ClickTracking, Convocatoria, Notificacion
from ai.classifier import AIClassifierService
from scrapers.bopv import BOPVScraper

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO if settings.APP_ENV != "development" else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("subvenciones-core")


# ------------------------------------------------------------------------------
# APLICACIÓN FASTAPI (TELEMETRÍA Y REDIRECCIÓN)
# ------------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación web."""
    logger.info("Iniciando servicio subvenciones-core...")
    settings.ensure_directories()
    yield
    logger.info("Deteniendo servicio subvenciones-core...")


app = FastAPI(
    title="Servicio de Inteligencia de Subvenciones Euskadi",
    description="API de telemetría, tracking y consulta para subvenciones y ayudas a pymes.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Salud y Monitoreo"])
def health_check(db: Session = Depends(get_db)):
    """Verifica el estado del servicio y la conectividad a la base de datos."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as ex:
        db_status = f"unhealthy: {str(ex)}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "environment": settings.APP_ENV,
        "database": db_status,
    }


@app.get("/t/{token}", tags=["Telemetría y Tracking"], response_class=RedirectResponse)
def track_click(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Endpoint de redirección y seguimiento de clics.
    Registra el acceso anonimizado y redirige al usuario a la URL oficial de la convocatoria.
    """
    notificacion = (
        db.query(Notificacion)
        .filter(Notificacion.token_tracking == token)
        .first()
    )

    if not notificacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de notificación no encontrado o inválido",
        )

    # Anonimizar la dirección IP mediante SHA-256
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    user_agent = request.headers.get("user-agent", "")

    # Registrar el evento de clic en click_tracking
    click_event = ClickTracking(
        notificacion_id=notificacion.id,
        ip_hash=ip_hash,
        user_agent=user_agent[:500] if user_agent else None,
    )
    db.add(click_event)
    db.commit()

    logger.info(
        f"Click registrado para Notificación ID={notificacion.id} "
        f"(Convocatoria ID={notificacion.convocatoria_id}, Cliente ID={notificacion.cliente_id})"
    )

    # Redirigir a la URL oficial de la convocatoria
    target_url = notificacion.convocatoria.url_oficial
    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/api/convocatorias", tags=["Convocatorias"])
def list_convocatorias(
    estado: Optional[EstadoConvocatoria] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Consulta convocatorias almacenadas filtrando opcionalmente por estado."""
    query = select(Convocatoria)
    if estado:
        query = query.filter(Convocatoria.estado == estado)
    query = query.order_by(Convocatoria.created_at.desc()).offset(offset).limit(limit)

    results = db.scalars(query).all()
    return [
        {
            "id": c.id,
            "id_origen": c.id_origen,
            "fuente": c.fuente,
            "titulo": c.titulo,
            "organismo": c.organismo,
            "url_oficial": c.url_oficial,
            "fecha_publicacion": c.fecha_publicacion,
            "estado": c.estado,
            "created_at": c.created_at,
        }
        for c in results
    ]


# ------------------------------------------------------------------------------
# INTERFAZ DE LÍNEA DE COMANDOS (CLI CON TYPER)
# ------------------------------------------------------------------------------

cli = typer.Typer(
    name="subvenciones-cli",
    help="CLI para administración y gestión del Servicio de Inteligencia de Subvenciones.",
    no_args_is_help=True,
)

scrape_cli = typer.Typer(
    help="Comandos para extracción de boletines oficiales.",
    no_args_is_help=True,
)
cli.add_typer(scrape_cli, name="scrape")


@cli.command("init-db")
def cmd_init_db():
    """Crea la estructura de tablas y activa extensiones en PostgreSQL."""
    typer.echo("-> Inicializando base de datos y esquemas...")
    try:
        init_database()
        typer.secho("✓ Tablas y extensiones creadas exitosamente.", fg=typer.colors.GREEN, bold=True)
    except Exception as ex:
        typer.secho(f"✗ Error al inicializar base de datos: {ex}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)


@scrape_cli.command("bopv")
def cmd_scrape_bopv(
    url: Optional[str] = typer.Option(
        None, "--url", "-u", help="URL opcional del sumario XML a procesar"
    ),
    days: int = typer.Option(
        1, "--days", "-d", help="Número de días laborables a procesar (por defecto 1, configurable hasta 30)"
    ),
):
    """Ejecuta el scraper del Boletín Oficial del País Vasco (BOPV)."""
    typer.echo(f"-> Iniciando ingesta del Boletín Oficial del País Vasco ({days} día(s) laborable(s))...")
    scraper = BOPVScraper(sumario_url=url, days=days)
    db = SessionLocal()
    try:
        stats = scraper.run(db)
        typer.echo("--------------------------------------------------")
        typer.secho("✓ Ingesta completada con éxito.", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"   • Anuncios procesados:  {stats['total']}")
        typer.echo(f"   • Nuevas convocatorias: {stats['inserted']}")
        typer.echo(f"   • Ya registradas:       {stats['skipped']}")
        typer.echo("--------------------------------------------------")
    except Exception as ex:
        typer.secho(f"✗ Falló la ingesta del BOPV: {ex}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@cli.command("classify")
def cmd_classify(
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Número máximo de convocatorias a clasificar"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Fuerza la reclasificación de convocatorias ya procesadas"
    ),
):
    """Ejecuta el motor de clasificación y extracción enriquecida con IA (modelo jev)."""
    typer.echo("-> Iniciando proceso de clasificación con IA (Vercel AI Gateway)...")
    init_database()

    db = SessionLocal()
    try:
        service = AIClassifierService()
        stats = service.process_batch(db, limit=limit, force=force)
        typer.echo("--------------------------------------------------")
        typer.secho("✓ Clasificación completada con éxito.", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"   • Total procesadas: {stats['total']}")
        typer.echo(f"   • Clasificadas:     {stats['clasificadas']}")
        typer.echo(f"   • Descartadas:      {stats['descartadas']}")
        typer.echo(f"   • Errores:          {stats['errores']}")
        typer.echo("--------------------------------------------------")
    except Exception as ex:
        typer.secho(f"✗ Falló la clasificación con IA: {ex}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@cli.command("run-server")
def cmd_run_server(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host de escucha"),
    port: int = typer.Option(8000, "--port", "-p", help="Puerto de escucha"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Habilita auto-reload"),
):
    """Inicia el servidor web FastAPI con Uvicorn."""
    typer.echo(f"-> Arrancando servidor web en http://{host}:{port} ...")
    uvicorn.run("main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
