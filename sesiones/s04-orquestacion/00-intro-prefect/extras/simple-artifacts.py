"""Artifacts: el reporte de la corrida vive junto a la corrida.

Un artifact es un resultado visible en la UI, asociado al flow run que lo produjo.
Es la diferencia entre "hay un HTML en la carpeta de alguien" y "este numero salio
de esta ejecucion, con estos parametros, a esta hora".

Tres tipos, y cuando usar cada uno:

- `create_table_artifact`: filas comparables (metricas, top de features).
- `create_markdown_artifact`: narrativa (resumen, decision tomada, siguiente paso).
- `create_link_artifact`: enlace a un recurso externo (el run de MLflow, un bucket).

Aqui las metricas son de juguete porque el objetivo es el mecanismo. Los artifacts
reales del caso guia los produce `src/taxi/flows/training.py` con las metricas de
esa corrida.
"""

from datetime import UTC, datetime

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact


@task
def entrenar_simulado() -> dict[str, float]:
    """Devuelve metricas de ejemplo."""
    logger = get_run_logger()
    logger.info("Entrenando (simulado)")
    return {"rmse": 7.15, "mae": 5.23, "r2": 0.82}


@task
def publicar_tabla(metricas: dict[str, float], baseline_rmse: float = 7.82) -> None:
    """Tabla comparativa contra el baseline.

    Una metrica sin baseline no se puede interpretar: 7.15 minutos de RMSE no es
    bueno ni malo hasta que se sabe cuanto da predecir siempre la media.
    """
    create_table_artifact(
        key="comparacion-con-baseline",
        table=[
            {"modelo": "candidato", "rmse": metricas["rmse"], "mae": metricas["mae"]},
            {"modelo": "baseline", "rmse": baseline_rmse, "mae": None},
        ],
        description="RMSE del candidato frente al baseline.",
    )


@task
def publicar_resumen(metricas: dict[str, float]) -> None:
    """Resumen en markdown de la corrida."""
    markdown = f"""# Resumen de entrenamiento

| Metrica | Valor |
|---|---|
| RMSE | {metricas["rmse"]:.2f} min |
| MAE | {metricas["mae"]:.2f} min |
| R2 | {metricas["r2"]:.2f} |

Generado: {datetime.now(UTC).isoformat(timespec="seconds")}

El candidato **no** se promueve desde el pipeline: eso lo decide el gate (S06).
"""
    create_markdown_artifact(
        key="resumen-de-entrenamiento",
        markdown=markdown,
        description="Resumen legible de la corrida.",
    )


@flow(name="demo-artifacts", log_prints=True)
def demo_artifacts() -> dict[str, float]:
    """Crea dos artifacts y los deja asociados a este flow run."""
    metricas = entrenar_simulado()
    publicar_tabla(metricas)
    publicar_resumen(metricas)
    return metricas


if __name__ == "__main__":
    print(demo_artifacts())
    print("Ver en la UI: Runs -> demo-artifacts -> pestana Artifacts")
