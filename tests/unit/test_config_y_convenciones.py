"""Invariantes de configuracion y convenciones del repositorio.

Son tests baratos que atrapan errores caros: una constante que nadie usa, un
early stopping que no puede dispararse, una referencia por stage que reaparece.
Cada uno corresponde a un problema real encontrado en la auditoria del repo.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from taxi import config
from taxi.models import evaluate, train


# =============================================================================
# uri_modelo
# =============================================================================
def test_uri_modelo_por_defecto_apunta_al_champion() -> None:
    assert config.uri_modelo() == "models:/nyc-taxi-duration@champion"


def test_uri_modelo_acepta_otro_modelo_y_otro_alias() -> None:
    uri = config.uri_modelo(config.MODELO_CLASIFICACION, config.ALIAS_CANDIDATO)
    assert uri == "models:/nyc-taxi-long-trip@candidate"


@pytest.mark.parametrize("alias", ["champion", "candidate", "shadow"])
def test_uri_modelo_nunca_genera_una_referencia_por_stage(alias: str) -> None:
    """La forma models:/<nombre>/Production esta deprecada y prohibida en el repo."""
    uri = config.uri_modelo(alias=alias)
    assert "@" in uri
    assert not re.search(r"/(Production|Staging|Archived|None)\b", uri)


# =============================================================================
# Particiones
# =============================================================================
def test_las_particiones_no_se_solapan() -> None:
    """Train, valid y holdout deben ser meses distintos, o hay leakage directo."""
    train_ = {p.etiqueta for p in config.PARTICIONES_TRAIN}
    assert config.PARTICION_VALID.etiqueta not in train_
    assert config.PARTICION_TEST.etiqueta not in train_
    assert config.PARTICION_TEST.etiqueta != config.PARTICION_VALID.etiqueta
    produccion = {p.etiqueta for p in config.PARTICIONES_PRODUCCION}
    assert not produccion & train_


def test_la_division_es_temporal_y_hacia_adelante() -> None:
    """Se entrena con el pasado y se evalua con el futuro, como en produccion."""
    ultimo_train = max((p.anio, p.mes) for p in config.PARTICIONES_TRAIN)
    valid = (config.PARTICION_VALID.anio, config.PARTICION_VALID.mes)
    test = (config.PARTICION_TEST.anio, config.PARTICION_TEST.mes)
    assert ultimo_train < valid < test


# =============================================================================
# Hiperparametros
# =============================================================================
def test_early_stopping_tiene_margen_para_dispararse() -> None:
    """EL BUG DEL PIPELINE ANTERIOR.

    Tenia `early_stopping_rounds=50` con `num_boost_round=30`: el entrenamiento
    terminaba antes de poder acumular 50 rondas sin mejora, asi que el early
    stopping no se activaba nunca. El codigo se veia correcto y la constante
    estaba ahi para tranquilizar a quien lo leyera.
    """
    assert train.RONDAS_EARLY_STOPPING < train.RONDAS_BOOST / 2
    assert train.PARAMS_XGBOOST["n_estimators"] == train.RONDAS_BOOST
    assert train.PARAMS_XGBOOST["early_stopping_rounds"] == train.RONDAS_EARLY_STOPPING


def test_el_espacio_de_busqueda_solo_tunea_parametros_reales() -> None:
    """Otro problema del repo: constantes definidas que ningun call site usaba.

    Todo lo que aparece en el espacio de Optuna debe existir en los parametros
    por defecto de XGBoost; si no, se estaria tuneando un nombre inventado que
    xgboost ignora en silencio.
    """
    assert set(train.ESPACIO_XGBOOST).issubset(train.PARAMS_XGBOOST)


def test_todos_los_constructores_de_pipeline_son_invocables() -> None:
    """Ninguna clave del CLI apunta a un constructor inexistente."""
    for nombre, constructor in train.CONSTRUCTORES.items():
        pipeline = constructor()
        assert list(pipeline.named_steps) == ["diccionarios", "vectorizador", "modelo"], nombre


def test_la_semilla_llega_a_los_modelos_que_la_aceptan() -> None:
    """Reproducibilidad: la semilla se pasa explicitamente, no por estado global."""
    assert train.PARAMS_RANDOM_FOREST["random_state"] == config.SEMILLA
    assert train.PARAMS_XGBOOST["random_state"] == config.SEMILLA


# =============================================================================
# Umbrales del gate
# =============================================================================
def test_el_umbral_por_subgrupo_es_mas_laxo_que_la_mejora_global() -> None:
    """Un subgrupo tiene menos datos y mas varianza.

    Exigirle lo mismo que al global bloquearia promociones legitimas por ruido,
    y un gate que rechaza modelos buenos se acaba desactivando.
    """
    assert evaluate.UMBRAL_DEGRADACION_SUBGRUPO > config.MEJORA_MINIMA_RELATIVA
    assert 0 < config.MEJORA_MINIMA_RELATIVA < 0.5


# =============================================================================
# Convenciones del codigo propio de esta entrega
# =============================================================================
ARCHIVOS_VIGILADOS = (
    "src/taxi/models/train.py",
    "src/taxi/models/registry.py",
    "src/taxi/models/evaluate.py",
    "src/taxi/cli.py",
    "scripts/promote.py",
    "scripts/model_card.py",
)

APIS_PROHIBIDAS = (
    "transition_model_version_stage",
    "get_latest_versions(",
    "archive_existing_versions",
    "artifact_path=",
    "squared=False",
    "sys.path.append",
)


@pytest.mark.parametrize("relativo", ARCHIVOS_VIGILADOS)
def test_ningun_modulo_usa_apis_deprecadas(relativo: str) -> None:
    """Duplica el hook de pre-commit a proposito.

    El hook se puede saltar con `--no-verify`; el test no. Y si algun dia el hook
    se desconfigura, este test sigue en pie.
    """
    ruta = config.PROJECT_ROOT / relativo
    assert ruta.is_file(), relativo
    codigo = ruta.read_text(encoding="utf-8")
    for prohibida in APIS_PROHIBIDAS:
        assert prohibida not in codigo, f"{relativo} usa {prohibida}"


@pytest.mark.parametrize("relativo", ARCHIVOS_VIGILADOS)
def test_cada_modulo_abre_con_un_docstring(relativo: str) -> None:
    texto = (config.PROJECT_ROOT / relativo).read_text(encoding="utf-8")
    sin_shebang = "\n".join(
        linea for linea in texto.splitlines() if not linea.startswith("#!")
    ).lstrip()
    assert sin_shebang.startswith('"""'), relativo


@pytest.mark.parametrize("relativo", ARCHIVOS_VIGILADOS)
def test_el_codigo_fuente_no_esta_gitignorado(relativo: str) -> None:
    """Ningun modulo de la aplicacion debe caer bajo una regla de .gitignore.

    Esta es la clase de bug mas insidiosa del repositorio, y ya habia ocurrido:
    la regla global ``*.json`` hacia invisible a ``data/raw/metadata.json``, con
    lo que la verificacion por hash existia en el codigo y no llegaba nunca al
    control de versiones (ver el docstring de ``taxi/data/loaders.py``).

    El mismo patron reaparece con la regla ``models/``, pensada para excluir
    artefactos de modelo, que tambien atrapa el PAQUETE ``src/taxi/models/``.
    Sintoma: ``git add`` no falla de forma visible, ``git status`` no muestra
    nada, el codigo funciona en la maquina del autor y el repositorio queda sin
    la mitad del sistema. Se descubre cuando alguien clona.

    Arreglo (en ``.gitignore``, despues de la regla ``models/``)::

        models/
        !src/taxi/models/

    Un ``.gitignore`` es codigo: merece un test.
    """
    resultado = subprocess.run(
        ["git", "check-ignore", "-v", "--", relativo],
        cwd=config.PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode > 1:  # 0 = ignorado, 1 = no ignorado, >1 = error de git
        pytest.skip(f"git no disponible: {resultado.stderr.strip()}")
    assert resultado.returncode == 1, (
        f"{relativo} esta excluido del control de versiones por "
        f"{resultado.stdout.strip()}. Agrega una negacion en .gitignore."
    )


def test_los_adr_de_esta_entrega_tienen_la_estructura_acordada() -> None:
    """Contexto / decision / alternativas / consecuencias, o no es un ADR."""
    secciones = ("Contexto", "Decisión", "Alternativas consideradas", "Consecuencias")
    for nombre in (
        "001-caso-guia-y-particiones.md",
        "002-aliases-en-vez-de-stages.md",
    ):
        ruta: Path = config.PROJECT_ROOT / "docs" / "adr" / nombre
        assert ruta.is_file(), nombre
        texto = ruta.read_text(encoding="utf-8")
        for seccion in secciones:
            assert seccion in texto, f"{nombre} no tiene la seccion {seccion}"
