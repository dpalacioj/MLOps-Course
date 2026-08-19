"""Tests del dataset de evals, la calculadora de costos, los prompts y el gate.

El test del dataset es el que mas veces va a salvar la sesion. Un dataset de eval
corrupto no lanza ninguna excepcion: produce metricas plausibles y equivocadas,
que es el peor modo de fallo posible porque nadie lo nota. Es el mismo argumento
de los contratos de datos de la sesion 2, aplicado al activo que sostiene todas
las decisiones de la sesion 8.
"""

from __future__ import annotations

import datetime as dt

import pytest
from clasificador import costos, datos, prompts
from clasificador.esquema import CATEGORIAS_VALIDAS, SEVERIDAD_MAX, SEVERIDAD_MIN
from clasificador.evaluar import decidir, ejecutar_eval
from clasificador.proveedor import ProveedorFake, clasificar_por_reglas, contar_tokens


# =============================================================================
# Dataset de evals
# =============================================================================
def test_el_dataset_esta_bien_formado_y_tiene_suficientes_casos() -> None:
    """Requisito del material: 30-40 casos etiquetados a mano."""
    casos = datos.cargar_casos()
    assert 30 <= len(casos) <= 45, f"se esperaban 30-40 casos y hay {len(casos)}"
    assert len({c.id for c in casos}) == len(casos), "hay ids duplicados"


def test_todas_las_etiquetas_estan_en_el_enum_y_en_rango() -> None:
    """La verificacion que evita perseguir un fallo del modelo que es del dataset.

    Si una etiqueta dice 'vehiculo' y el enum no lo tiene, el modelo NUNCA puede
    acertar ese caso y el eval lo reporta como error del modelo. Se pierden horas
    ahi.
    """
    for caso in datos.cargar_casos():
        assert caso.categoria in CATEGORIAS_VALIDAS, f"{caso.id}: {caso.categoria}"
        assert SEVERIDAD_MIN <= caso.severidad <= SEVERIDAD_MAX, f"{caso.id}"
        assert isinstance(caso.requiere_reembolso, bool), f"{caso.id}"
        assert caso.entrada.strip(), f"{caso.id}: entrada vacia"


def test_cada_caso_documenta_su_criterio() -> None:
    """El campo ``notas`` es lo que hace mantenible el dataset.

    Sin el, en tres meses nadie recuerda por que q031 es 'tarifa' y no
    'tiempo_de_espera', y el siguiente anotador introduce otro criterio.
    """
    for caso in datos.cargar_casos():
        assert caso.notas.strip(), f"{caso.id} no explica por que su etiqueta es esa"


def test_el_dataset_cubre_todas_las_categorias() -> None:
    """Una categoria sin casos es una categoria sin medir."""
    distribucion = datos.distribucion_de_categorias(datos.cargar_casos())
    sin_casos = [cat for cat, n in distribucion.items() if n == 0]
    assert not sin_casos, f"categorias sin ningun caso: {sin_casos}"


def test_el_dataset_tiene_las_dos_clases_de_reembolso() -> None:
    """Sin casos negativos, ``reembolso_correcto`` premia responder siempre true."""
    casos = datos.cargar_casos()
    valores = {c.requiere_reembolso for c in casos}
    assert valores == {True, False}


@pytest.mark.parametrize(
    "linea,fragmento_del_error",
    [
        ('{"id": "x", "entrada": "a"}', "esperado"),
        ('{"id": "x", "entrada": "a", "esperado": {"categoria": "tarifa"}}', "severidad"),
        (
            '{"id": "x", "entrada": "a", "esperado": {"categoria": "inventada", '
            '"severidad": 3, "requiere_reembolso": false}}',
            "no esta en el enum",
        ),
        (
            '{"id": "x", "entrada": "a", "esperado": {"categoria": "app", '
            '"severidad": 9, "requiere_reembolso": false}}',
            "fuera del rango",
        ),
        ('{"id": "x", "entrada": "", "esperado": {}}', "vacia"),
        ("{no es json}", "JSON malformado"),
    ],
)
def test_el_cargador_rechaza_datasets_invalidos(
    tmp_path, linea: str, fragmento_del_error: str
) -> None:
    """Se valida al CARGAR, no al usar. Fallar temprano y con el motivo."""
    archivo = tmp_path / "malo.jsonl"
    archivo.write_text(linea, encoding="utf-8")
    with pytest.raises(datos.DatasetInvalido, match=fragmento_del_error):
        datos.cargar_casos(archivo)


def test_el_cargador_rechaza_ids_duplicados(tmp_path) -> None:
    """Dos casos con el mismo id hacen imposible rastrear un fallo."""
    archivo = tmp_path / "dup.jsonl"
    fila = (
        '{"id": "q1", "entrada": "a", "esperado": {"categoria": "app", '
        '"severidad": 1, "requiere_reembolso": false}}'
    )
    archivo.write_text(f"{fila}\n{fila}\n", encoding="utf-8")
    with pytest.raises(datos.DatasetInvalido, match="duplicado"):
        datos.cargar_casos(archivo)


# =============================================================================
# Prompts
# =============================================================================
def test_las_dos_versiones_del_prompt_existen_y_son_distintas() -> None:
    """Requisito del taller: dos versiones comparables."""
    v1 = prompts.cargar_local("v1")
    v2 = prompts.cargar_local("v2")
    assert v1.texto != v2.texto
    assert v1.huella != v2.huella, "las huellas deben distinguir las versiones"
    assert len(v2.texto) > len(v1.texto), "v2 es la version con rubrica"


def test_las_variables_del_prompt_se_derivan_del_contrato() -> None:
    """Si el enum gana una categoria, el prompt la lista sin editarlo a mano."""
    for etiqueta in ("v1", "v2"):
        plantilla = prompts.cargar_local(etiqueta)
        assert "categorias" in plantilla.variables
        renderizado = plantilla.renderizar(**prompts.contexto_por_defecto())
        for categoria in CATEGORIAS_VALIDAS:
            assert categoria in renderizado, f"{etiqueta} no menciona {categoria}"
        assert "{{" not in renderizado, "quedaron placeholders sin sustituir"


def test_renderizar_falla_si_falta_una_variable() -> None:
    """Un ``{{contexto}}`` literal en el prompt no rompe nada y empeora todo.

    El sistema no se cae: responde peor y nadie sabe por que. Fallar es el punto.
    """
    plantilla = prompts.cargar_local("v2")
    with pytest.raises(ValueError, match="faltan variables"):
        plantilla.renderizar(categorias="a, b")


def test_version_de_prompt_desconocida_falla_con_las_opciones() -> None:
    """El mensaje de error debe decir que versiones hay."""
    with pytest.raises(KeyError, match="v1"):
        prompts.cargar_local("v99")


# =============================================================================
# Costos
# =============================================================================
def test_calculo_de_costo_con_numeros_redondos() -> None:
    """Verificable a mano: 1M de tokens de entrada a 0.15 USD/M = 0.15 USD."""
    tabla = costos.cargar_precios()
    costo = costos.calcular_costo(1_000_000, 0, "gpt-4o-mini", tabla=tabla)
    assert costo.usd_entrada == pytest.approx(0.15)
    assert costo.usd_salida == pytest.approx(0.0)

    salida = costos.calcular_costo(0, 1_000_000, "gpt-4o-mini", tabla=tabla)
    assert salida.usd_salida == pytest.approx(0.60)


def test_el_costo_escala_con_los_requests() -> None:
    """La extrapolacion a 1000 requests es la cifra que se puede interpretar."""
    tabla = costos.cargar_precios()
    uno = costos.calcular_costo(1000, 100, "gpt-4o-mini", tabla=tabla)
    mil = costos.calcular_costo(1000, 100, "gpt-4o-mini", tabla=tabla, requests=1000)
    assert mil.usd_total == pytest.approx(uno.usd_total * 1000)
    assert uno.por_mil_requests() == pytest.approx(mil.usd_total)


def test_modelo_desconocido_se_estima_con_el_mas_caro() -> None:
    """Una estimacion de costos debe equivocarse hacia ARRIBA.

    Un modelo desconocido con precio cero produce un reporte que dice que el
    sistema es gratis, y esa es la peor forma de equivocarse: la que tranquiliza.
    """
    tabla = costos.cargar_precios()
    desconocido = costos.calcular_costo(1_000_000, 0, "modelo-que-no-existe", tabla=tabla)
    barato = costos.calcular_costo(1_000_000, 0, "gpt-4o-mini", tabla=tabla)
    assert desconocido.usd_entrada > barato.usd_entrada


def test_el_fake_cuesta_cero() -> None:
    """Costo cero es la senal mas clara de que no se midio el sistema real."""
    tabla = costos.cargar_precios()
    costo = costos.calcular_costo(999_999, 999_999, "fake-reglas-v1", tabla=tabla)
    assert costo.usd_total == 0.0


def test_los_precios_vencidos_se_advierten() -> None:
    """Un numero de costo sin fecha de precios no es una estimacion: es una cifra."""
    tabla = costos.cargar_precios()
    assert tabla.actualizado is not None, "precios.yaml debe declarar 'actualizado'"

    muy_futuro = tabla.actualizado + dt.timedelta(days=tabla.vigencia_dias + 1)
    assert tabla.esta_vencida(muy_futuro) is True
    assert tabla.esta_vencida(tabla.actualizado) is False


def test_costo_negativo_es_un_bug() -> None:
    """Tokens negativos no tienen semantica."""
    tabla = costos.cargar_precios()
    with pytest.raises(ValueError, match="negativos"):
        costos.calcular_costo(-1, 0, "gpt-4o-mini", tabla=tabla)


def test_contar_tokens_funciona_sin_tiktoken() -> None:
    """El extra ``llmops`` es opcional: el conteo debe degradar, no fallar."""
    assert contar_tokens("hola mundo") > 0
    assert contar_tokens("") > 0, "nunca debe devolver 0 y provocar una division por cero"


# =============================================================================
# Gate
# =============================================================================
def test_el_gate_pasa_con_el_fake_y_el_prompt_v2() -> None:
    """El eval completo debe pasar en un fork sin credenciales.

    Si el gate por defecto no pasara con el fake, el CI de un fork estaria rojo
    desde el primer dia y el equipo aprenderia a ignorarlo.
    """
    resultado = ejecutar_eval(etiqueta_prompt="v2", proveedor=ProveedorFake(), juez=None)
    veredicto = decidir(resultado)
    assert veredicto.paso, veredicto.motivo
    assert resultado.metricas["json_valido"] == 1.0


def test_el_gate_falla_si_el_json_deja_de_ser_valido() -> None:
    """El gate tiene que poder ponerse rojo, o no es un gate.

    Se usa un proveedor que nunca cumple el contrato: es la simulacion de "alguien
    rompio el parseo o el esquema".
    """
    roto = ProveedorFake(fallos_iniciales=999)
    resultado = ejecutar_eval(etiqueta_prompt="v2", proveedor=roto, juez=None)
    veredicto = decidir(resultado)

    assert veredicto.paso is False
    assert resultado.metricas["json_valido"] == 0.0
    assert any("json_valido" in i for i in veredicto.incumplimientos)


def test_el_prompt_con_rubrica_mejora_al_minimo_en_el_fake() -> None:
    """La comparacion de versiones tiene que producir un delta distinto de cero.

    ADVERTENCIA: ``ProveedorFake`` **simula** sensibilidad al prompt (ver
    ``MARCADOR_RUBRICA`` en ``proveedor.py``). Este test verifica que la maquinaria
    de comparacion funciona offline; NO es evidencia de que un prompt con rubrica
    mejore a un LLM real. Con un modelo real puede empeorar.
    """
    v1 = ejecutar_eval(etiqueta_prompt="v1", proveedor=ProveedorFake(), juez=None)
    v2 = ejecutar_eval(etiqueta_prompt="v2", proveedor=ProveedorFake(), juez=None)
    assert v2.metricas["categoria_correcta"] > v1.metricas["categoria_correcta"]
    assert v1.huella_prompt != v2.huella_prompt


def test_la_linea_base_por_reglas_cumple_el_contrato() -> None:
    """La linea base tiene que ser comparable, y para eso debe cumplir el esquema."""
    from clasificador.esquema import ClasificacionQueja

    for con_rubrica in (False, True):
        salida = clasificar_por_reglas("El taxi estaba sucio y olia mal", con_rubrica=con_rubrica)
        validada = ClasificacionQueja.model_validate(salida)
        assert validada.categoria in CATEGORIAS_VALIDAS


def test_un_comentario_positivo_no_se_clasifica_como_queja_grave() -> None:
    """El fallo mas embarazoso posible en produccion.

    Solo lo evita el juego de reglas fino, y es una de las cosas que la rubrica del
    prompt v2 pide explicitamente.
    """
    felicitacion = "Excelente servicio, el conductor fue muy amable. Gracias."
    fina = clasificar_por_reglas(felicitacion, con_rubrica=True)
    assert fina["severidad"] == 1
    assert fina["requiere_reembolso"] is False
