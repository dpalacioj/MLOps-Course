"""Tests de la politica del gate de promocion.

MLflow NO se levanta: se mockea. Esa es la razon por la que la politica vive en
funciones puras en ``taxi.models.evaluate`` y no incrustada en el script. Un gate
que solo se puede probar con un tracking server corriendo no se prueba, y una
politica de promocion sin tests es una politica que nadie se atreve a cambiar.

Los tres escenarios que importan —champion peor, champion mejor, sin champion—
se cubren tanto a nivel de criterio individual como del script completo.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from taxi import config
from taxi.models import evaluate


# =============================================================================
# Carga de scripts/promote.py
# =============================================================================
def _cargar_promote() -> ModuleType:
    """Importa scripts/promote.py por ruta.

    ``scripts/`` no es un paquete instalable y esta prohibido usar
    ``sys.path.append``, asi que se carga por especificacion de archivo. Es la
    misma tecnica que usa ``taxi.cli``.
    """
    ruta = config.PROJECT_ROOT / "scripts" / "promote.py"
    spec = importlib.util.spec_from_file_location("promote_bajo_test", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


promote = _cargar_promote()


class ModeloFalso:
    """Modelo que predice el target real mas un error controlado.

    Permite fijar el RMSE de un modelo ficticio sin entrenar nada: el error se
    genera con un ``Generator`` propio y semilla fija, asi que el RMSE resultante
    es el mismo en cada corrida.
    """

    def __init__(self, y_true: np.ndarray, sigma: float, semilla: int = 7) -> None:
        self._y = np.asarray(y_true, dtype=float)
        self._sigma = sigma
        self._semilla = semilla

    def predict(self, entradas: Any) -> np.ndarray:
        n = len(entradas)
        generador = np.random.default_rng(self._semilla)
        return self._y[:n] + generador.normal(0.0, self._sigma, n)


def _version(numero: str) -> SimpleNamespace:
    return SimpleNamespace(version=numero, run_id=f"run-{numero}", tags={}, description="")


# =============================================================================
# Criterio 1 — contrato de datos
# =============================================================================
def test_criterio_contrato_acepta_el_holdout_valido(df_procesado_valido: pd.DataFrame) -> None:
    resultado = evaluate.criterio_contrato_datos(df_procesado_valido)
    assert resultado.aprobado
    assert str(len(df_procesado_valido)) in resultado.detalle


def test_criterio_contrato_rechaza_un_holdout_invalido(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Un holdout que viola el contrato invalida cualquier metrica medida sobre el."""
    df = df_procesado_valido.copy()
    df["hora_pickup"] = 99  # fuera del rango 0-23
    resultado = evaluate.criterio_contrato_datos(df)
    assert not resultado.aprobado
    assert resultado.evaluado


# =============================================================================
# Criterio 2 — mejora global
# =============================================================================
def test_promueve_cuando_el_champion_es_peor() -> None:
    resultado = evaluate.criterio_mejora_global(4.0, 5.0, mejora_minima=0.01)
    assert resultado.aprobado
    assert "-20" in resultado.detalle  # -20.00% de mejora relativa


def test_rechaza_cuando_el_champion_es_mejor() -> None:
    resultado = evaluate.criterio_mejora_global(5.5, 5.0, mejora_minima=0.01)
    assert not resultado.aprobado


def test_promueve_y_lo_declara_cuando_no_hay_champion() -> None:
    """Sin champion, el candidato entra y el gate lo dice de forma explicita."""
    resultado = evaluate.criterio_mejora_global(7.3, None)
    assert resultado.aprobado
    assert "PRIMER modelo" in resultado.detalle


def test_rechaza_una_mejora_dentro_del_margen() -> None:
    """Empatar no alcanza, y mejorar 0.2% con margen del 1% tampoco.

    Es lo que evita el churn de modelos: dos modelos equivalentes se alternarian
    en produccion indefinidamente por ruido de muestreo, y cada rotacion cuesta
    un despliegue y rompe la comparabilidad de las metricas de negocio.
    """
    assert not evaluate.criterio_mejora_global(5.0, 5.0, mejora_minima=0.01).aprobado
    assert not evaluate.criterio_mejora_global(4.99, 5.0, mejora_minima=0.01).aprobado
    assert evaluate.criterio_mejora_global(4.94, 5.0, mejora_minima=0.01).aprobado


# =============================================================================
# Criterio 3 — subgrupos
# =============================================================================
def test_subgrupos_aprueba_si_todos_mejoran(subgrupos_base: dict[str, float]) -> None:
    candidato = {k: (v * 0.9 if k.startswith("rmse_") else v) for k, v in subgrupos_base.items()}
    resultado = evaluate.criterio_subgrupos(candidato, subgrupos_base, umbral=0.05)
    assert resultado.aprobado


def test_subgrupos_rechaza_una_regresion_silenciosa(subgrupos_base: dict[str, float]) -> None:
    """El caso que el RMSE global esconde.

    El candidato mejora fuerte en los tres subgrupos grandes y se degrada 30% en
    la madrugada. El promedio global sale mejor; el usuario que viaja de
    madrugada recibe un servicio peor. El gate lo tiene que atrapar.
    """
    candidato = {k: (v * 0.85 if k.startswith("rmse_") else v) for k, v in subgrupos_base.items()}
    candidato["rmse_hora_madrugada"] = subgrupos_base["rmse_hora_madrugada"] * 1.30

    resultado = evaluate.criterio_subgrupos(candidato, subgrupos_base, umbral=0.05)
    assert not resultado.aprobado
    assert "rmse_hora_madrugada" in resultado.detalle


def test_subgrupos_tolera_una_degradacion_bajo_el_umbral(
    subgrupos_base: dict[str, float],
) -> None:
    """Un 3% con umbral del 5% pasa: los subgrupos tienen mas varianza."""
    candidato = dict(subgrupos_base)
    candidato["rmse_dist_larga"] = subgrupos_base["rmse_dist_larga"] * 1.03
    assert evaluate.criterio_subgrupos(candidato, subgrupos_base, umbral=0.05).aprobado


def test_subgrupos_aprueba_sin_linea_base(subgrupos_base: dict[str, float]) -> None:
    assert evaluate.criterio_subgrupos(subgrupos_base, None).aprobado


def test_subgrupos_rechaza_si_no_hay_nada_comparable(subgrupos_base: dict[str, float]) -> None:
    """El gate no aprueba lo que no puede verificar.

    Si los subgrupos del candidato y del champion no se solapan (por ejemplo
    porque se redefinieron los cortes), no hay evidencia de ausencia de
    regresion. Aprobar por defecto convertiria el criterio en decorativo.
    """
    resultado = evaluate.criterio_subgrupos({"rmse_otra_cosa": 1.0}, subgrupos_base, umbral=0.05)
    assert not resultado.aprobado


def test_los_contadores_no_se_comparan_como_metricas(
    subgrupos_base: dict[str, float],
) -> None:
    """Las claves n_* son tamanos de subgrupo, no errores.

    Si el candidato se evalua sobre un holdout de distinto tamano, tratar n_* como
    metrica dispararia una "degradacion" falsa.
    """
    candidato = dict(subgrupos_base)
    candidato["n_hora_madrugada"] = subgrupos_base["n_hora_madrugada"] * 5
    assert evaluate.criterio_subgrupos(candidato, subgrupos_base, umbral=0.05).aprobado


# =============================================================================
# Decision completa
# =============================================================================
def test_decidir_promocion_corta_si_el_contrato_falla(
    df_procesado_valido: pd.DataFrame, subgrupos_base: dict[str, float]
) -> None:
    """Si el dato esta mal, las metricas NO se miran.

    Reportar una comparacion de RMSE sobre datos invalidos invita a discutir el
    numero equivocado. Los criterios 2 y 3 quedan marcados como no evaluados,
    que es un diagnostico distinto de "los revise y fallaron".
    """
    invalido = df_procesado_valido.copy()
    invalido["dia_semana_pickup"] = 42

    decision = evaluate.decidir_promocion(
        invalido,
        {"rmse": 1.0, "mae": 1.0, "r2": 0.9},
        subgrupos_base,
        {"rmse": 99.0, "mae": 99.0, "r2": 0.1},
        subgrupos_base,
    )

    assert not decision.promover
    assert decision.estado_validacion == "failed"
    assert [c.evaluado for c in decision.criterios] == [True, False, False]
    assert "contrato_de_datos" in decision.motivo


def test_decidir_promocion_marca_el_primer_modelo(
    df_procesado_valido: pd.DataFrame, subgrupos_base: dict[str, float]
) -> None:
    decision = evaluate.decidir_promocion(
        df_procesado_valido, {"rmse": 6.0, "mae": 4.0, "r2": 0.5}, subgrupos_base
    )
    assert decision.promover
    assert decision.es_primer_modelo
    assert decision.estado_validacion == "passed"
    assert "no hay champion" in decision.motivo


def test_decidir_promocion_rechaza_al_candidato_peor(
    df_procesado_valido: pd.DataFrame, subgrupos_base: dict[str, float]
) -> None:
    decision = evaluate.decidir_promocion(
        df_procesado_valido,
        {"rmse": 7.0, "mae": 5.0, "r2": 0.3},
        subgrupos_base,
        {"rmse": 5.0, "mae": 3.5, "r2": 0.6},
        subgrupos_base,
    )
    assert not decision.promover
    assert not decision.es_primer_modelo
    assert "mejora_global" in decision.motivo


# =============================================================================
# scripts/promote.py con MLflow mockeado
# =============================================================================
@pytest.fixture
def registry_falso(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Sustituye el modulo registry completo dentro de promote.py."""
    falso = MagicMock()
    falso.cliente.return_value = MagicMock()
    monkeypatch.setattr(promote, "registry", falso)
    return falso


@pytest.fixture
def modelos_falsos(
    monkeypatch: pytest.MonkeyPatch, df_procesado_valido: pd.DataFrame
) -> dict[str, ModeloFalso]:
    """Devuelve un candidato bueno y un champion malo segun la URI pedida."""
    from taxi.features import contract as fc

    y = df_procesado_valido[fc.TARGET_REGRESION].to_numpy(dtype=float)
    catalogo = {
        "candidato": ModeloFalso(y, sigma=1.0),
        "champion": ModeloFalso(y, sigma=4.0),
    }

    def cargar(uri: str) -> ModeloFalso:
        return catalogo["champion"] if "@" in uri else catalogo["candidato"]

    monkeypatch.setattr(promote, "_cargar_modelo", cargar)
    return catalogo


def test_gate_promueve_al_primer_modelo(
    registry_falso: MagicMock,
    modelos_falsos: dict[str, ModeloFalso],
    df_procesado_valido: pd.DataFrame,
) -> None:
    registry_falso.ultima_version.return_value = _version("1")
    registry_falso.version_por_alias.return_value = None

    codigo = promote.ejecutar_gate(holdout=df_procesado_valido)

    assert codigo == promote.EXITO_PROMOVIDO
    registry_falso.marcar_validacion.assert_called_once()
    assert registry_falso.marcar_validacion.call_args.args[2] == "passed"
    registry_falso.asignar_alias.assert_called_once()
    assert registry_falso.asignar_alias.call_args.args[1] == config.ALIAS_PRODUCCION


def test_gate_rechaza_cuando_el_champion_es_mejor(
    monkeypatch: pytest.MonkeyPatch,
    registry_falso: MagicMock,
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Exit code 1 y el alias NO se mueve: el modelo que sirve trafico no se toca."""
    from taxi.features import contract as fc

    y = df_procesado_valido[fc.TARGET_REGRESION].to_numpy(dtype=float)
    monkeypatch.setattr(
        promote,
        "_cargar_modelo",
        lambda uri: ModeloFalso(y, sigma=1.0) if "@" in uri else ModeloFalso(y, sigma=6.0),
    )
    registry_falso.ultima_version.return_value = _version("9")
    registry_falso.version_por_alias.return_value = _version("8")

    codigo = promote.ejecutar_gate(holdout=df_procesado_valido)

    assert codigo == promote.EXITO_RECHAZADO
    assert registry_falso.marcar_validacion.call_args.args[2] == "failed"
    registry_falso.asignar_alias.assert_not_called()


def test_gate_en_dry_run_no_escribe_nada(
    registry_falso: MagicMock,
    modelos_falsos: dict[str, ModeloFalso],
    df_procesado_valido: pd.DataFrame,
) -> None:
    registry_falso.ultima_version.return_value = _version("3")
    registry_falso.version_por_alias.return_value = _version("2")

    codigo = promote.ejecutar_gate(dry_run=True, holdout=df_procesado_valido)

    assert codigo == promote.EXITO_PROMOVIDO
    registry_falso.marcar_validacion.assert_not_called()
    registry_falso.asignar_alias.assert_not_called()


def test_gate_devuelve_error_de_infra_sin_versiones(
    registry_falso: MagicMock, df_procesado_valido: pd.DataFrame
) -> None:
    """No poder medir no es lo mismo que un modelo malo.

    Si el gate devolviera 1 aqui, un MLflow caido se leeria en el CI como "el
    modelo no es lo bastante bueno" y alguien pasaria una tarde depurando el
    modelo equivocado.
    """
    registry_falso.ultima_version.return_value = None

    codigo = promote.ejecutar_gate(holdout=df_procesado_valido)

    assert codigo == promote.ERROR_INFRA
    assert promote.ERROR_INFRA != promote.EXITO_RECHAZADO


def test_gate_no_hace_nada_si_el_candidato_ya_es_champion(
    registry_falso: MagicMock, df_procesado_valido: pd.DataFrame
) -> None:
    registry_falso.ultima_version.return_value = _version("5")
    registry_falso.version_por_alias.return_value = _version("5")

    codigo = promote.ejecutar_gate(holdout=df_procesado_valido)

    assert codigo == promote.EXITO_PROMOVIDO
    registry_falso.asignar_alias.assert_not_called()


def test_el_script_promote_existe_y_documenta_el_rollback() -> None:
    """El rollback debe estar escrito donde se busca en un incidente."""
    ruta = Path(promote.__file__)
    texto = ruta.read_text(encoding="utf-8")
    assert "Rollback" in texto
    assert "asignar_alias" in texto
    assert "transition_model_version_stage" not in texto
