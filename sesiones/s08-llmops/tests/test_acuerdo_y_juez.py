"""Tests del acuerdo juez-humano: kappa con valores conocidos y casos degenerados.

Kappa se cita mucho y se verifica poco. Estos tests fijan su comportamiento en los
casos construidos a mano donde el valor correcto se puede calcular con lapiz, y
sobre todo en los **degenerados**, que son los que producen conclusiones erroneas
en un reporte real.
"""

from __future__ import annotations

import pytest
from clasificador.scorers.acuerdo import (
    KAPPA_MINIMO_PARA_GATE,
    MINIMO_CASOS_CALIBRACION,
    cohen_kappa,
    medir_acuerdo,
)
from clasificador.scorers.juez import (
    JuezFake,
    calibrar,
    cargar_calibracion,
    cargar_rubrica,
    resultado_reportable,
)


# =============================================================================
# Kappa con valores calculables a mano
# =============================================================================
def test_kappa_acuerdo_perfecto_con_variacion() -> None:
    """Acuerdo total y ambas etiquetas presentes -> kappa exactamente 1.0."""
    juez = [True, True, False, False]
    humano = [True, True, False, False]
    assert cohen_kappa(juez, humano) == pytest.approx(1.0)


def test_kappa_es_cero_cuando_el_juez_aprueba_todo() -> None:
    """El caso que motiva usar kappa en lugar del porcentaje de acuerdo.

    Diez casos, ocho aprobados por el humano. Un juez que aprueba TODO saca 80% de
    acuerdo, que suena bien, y no distingue absolutamente nada.

    Calculo a mano: Po = 0.8. El juez dice 'si' el 100% de las veces, el humano el
    80%, asi que Pe = 1.0*0.8 + 0.0*0.2 = 0.8. Kappa = (0.8-0.8)/(1-0.8) = 0.
    """
    juez = [True] * 10
    humano = [True] * 8 + [False] * 2
    acuerdo = medir_acuerdo(juez, humano)

    assert acuerdo.porcentaje_acuerdo == pytest.approx(0.8)
    assert acuerdo.kappa == pytest.approx(0.0)
    assert "permisivo" in acuerdo.sesgo_del_juez


def test_kappa_valor_conocido_de_una_matriz_2x2() -> None:
    """Matriz construida a mano con kappa calculable.

    20 casos: 8 (si,si), 2 (si,no), 2 (no,si), 8 (no,no).
        Po = (8+8)/20 = 0.8
        p_juez_si = 10/20 = 0.5 ; p_humano_si = 10/20 = 0.5
        Pe = 0.5*0.5 + 0.5*0.5 = 0.5
        kappa = (0.8-0.5)/(1-0.5) = 0.6
    """
    juez = [True] * 10 + [False] * 10
    humano = [True] * 8 + [False] * 2 + [True] * 2 + [False] * 8
    acuerdo = medir_acuerdo(juez, humano)

    assert acuerdo.juez_si_humano_si == 8
    assert acuerdo.juez_si_humano_no == 2
    assert acuerdo.juez_no_humano_si == 2
    assert acuerdo.juez_no_humano_no == 8
    assert acuerdo.porcentaje_acuerdo == pytest.approx(0.8)
    assert acuerdo.kappa == pytest.approx(0.6)
    assert acuerdo.kappa >= KAPPA_MINIMO_PARA_GATE


def test_kappa_negativo_cuando_es_peor_que_el_azar() -> None:
    """Desacuerdo total con marginales balanceados -> kappa -1.0.

    Po = 0, Pe = 0.5, kappa = (0-0.5)/0.5 = -1. Un kappa negativo no es un error
    de calculo: significa que el juez se equivoca de forma sistematica, y eso es
    informacion util (a veces la etiqueta esta invertida).
    """
    juez = [True, True, False, False]
    humano = [False, False, True, True]
    assert cohen_kappa(juez, humano) == pytest.approx(-1.0)


def test_kappa_degenerado_ambos_etiquetan_todo_igual() -> None:
    """Sin variacion en las etiquetas, kappa no informa.

    Los dos aprueban los 12 casos: Po = 1 y Pe = 1, y la formula da 0/0. Se
    devuelve 1.0 por convencion (el acuerdo observado es total), y la lectura
    correcta NO es "kappa perfecto" sino "el conjunto de calibracion no tiene
    casos negativos". Este test fija la convencion para que nadie la cambie sin
    darse cuenta.
    """
    juez = [True] * 12
    humano = [True] * 12
    assert cohen_kappa(juez, humano) == pytest.approx(1.0)

    # El caso simetrico: los dos rechazan todo.
    assert cohen_kappa([False] * 12, [False] * 12) == pytest.approx(1.0)


def test_kappa_rechaza_entradas_invalidas() -> None:
    """Longitudes distintas o listas vacias son bugs de quien llama."""
    with pytest.raises(ValueError, match="mismo largo"):
        cohen_kappa([True, False], [True])
    with pytest.raises(ValueError, match="cero casos"):
        cohen_kappa([], [])


def test_interpretacion_marca_muestra_insuficiente() -> None:
    """Con menos de 10 casos el valor puntual de kappa no informa."""
    acuerdo = medir_acuerdo([True, False, True], [True, False, True])
    assert acuerdo.n < MINIMO_CASOS_CALIBRACION
    assert "insuficiente" in acuerdo.interpretacion
    assert acuerdo.utilizable_como_gate is False


# =============================================================================
# El juez y su calibracion
# =============================================================================
def test_la_rubrica_existe_y_contiene_la_regla_no_negociable() -> None:
    """La rubrica es el artefacto, no un anexo.

    Se verifica que el archivo existe y que contiene la regla, porque el resto del
    material la cita: si alguien la borra al reescribir la rubrica, este test lo
    detecta antes que un estudiante.
    """
    texto = cargar_rubrica()
    # La rubrica es Markdown y va CON tildes, a diferencia del codigo Python.
    assert "opinión con API" in texto
    assert "kappa" in texto.lower()


def test_el_conjunto_de_calibracion_tiene_al_menos_10_casos() -> None:
    """Requisito explicito del material: minimo 10 casos etiquetados a mano."""
    casos = cargar_calibracion()
    assert len(casos) >= MINIMO_CASOS_CALIBRACION
    assert len({c.id for c in casos}) == len(casos), "ids duplicados"
    # Debe haber las dos etiquetas: un conjunto de solo aprobados no calibra nada.
    veredictos = {c.veredicto_humano for c in casos}
    assert veredictos == {True, False}


def test_el_juez_fake_no_alcanza_el_kappa_para_ser_gate(juez: JuezFake) -> None:
    """La leccion central de la sesion, como test.

    ``JuezFake`` aplica por reglas los criterios de suficiencia, PII y tono, y **no
    puede** aplicar el de fidelidad. Sobre el conjunto de calibracion eso le da un
    kappa por debajo del corte, y por tanto su resultado NO es reportable.

    Si alguien "mejora" el juez fake hasta pasar el corte sin resolver la
    fidelidad, este test falla y obliga a justificarlo en el PR. Es el mecanismo
    que impide que la leccion se pierda en un refactor.
    """
    calibracion = calibrar(juez)
    assert calibracion.acuerdo.n >= MINIMO_CASOS_CALIBRACION
    assert calibracion.acuerdo.utilizable_como_gate is False
    assert calibracion.desacuerdos, "debe haber desacuerdos que mirar"


def test_los_desacuerdos_del_juez_fake_se_concentran_en_fidelidad(juez: JuezFake) -> None:
    """Kappa dice cuanto coincide; el punto ciego dice si sirve.

    Dos jueces con el mismo kappa son muy distintos si uno falla al azar y el otro
    falla siempre en el mismo criterio. El segundo no se arregla con mas casos de
    calibracion.
    """
    calibracion = calibrar(juez)
    assert calibracion.punto_ciego is not None
    assert "fidelidad" in calibracion.punto_ciego


def test_resultado_no_reportable_cuando_el_kappa_es_bajo(juez: JuezFake) -> None:
    """La regla se aplica en codigo, no como consejo.

    No existe en este modulo una via para obtener la tasa de aprobacion del juez
    sin el kappa al lado, porque la via facil es la que se usa.
    """
    calibracion = calibrar(juez)
    linea = resultado_reportable(calibracion, 0.95)

    assert "NO REPORTABLE" in linea
    assert "95%" in linea, "la tasa debe aparecer, marcada como no valida"
    assert "kappa" in linea


def test_resultado_reportable_cuando_el_kappa_es_alto() -> None:
    """El camino positivo: kappa suficiente -> el numero se reporta CON el kappa."""
    from clasificador.scorers.juez import ResultadoCalibracion

    acuerdo = medir_acuerdo([True] * 10 + [False] * 10, [True] * 8 + [False] * 12)
    calibracion = ResultadoCalibracion(
        acuerdo=acuerdo, juez="juez-de-prueba", desacuerdos=["x1", "x2"]
    )
    assert acuerdo.kappa >= KAPPA_MINIMO_PARA_GATE

    linea = resultado_reportable(calibracion, 0.80)
    assert "NO REPORTABLE" not in linea
    assert "kappa" in linea and "n=20" in linea


def test_el_juez_rechaza_pii_y_tono_no_neutro(juez: JuezFake) -> None:
    """Los criterios que el juez por reglas SI puede aplicar."""
    entrada = "El conductor venia hablando por celular y se paso dos semaforos en rojo."

    con_pii = juez.juzgar(entrada, "El conductor del vehiculo ABC123 uso el celular")
    assert con_pii.aprobado is False
    assert "datos personales" in con_pii.criterio

    juzgador = juez.juzgar(entrada, "El conductor es un irresponsable al volante")
    assert juzgador.aprobado is False
    assert "tono neutro" in juzgador.criterio

    generico = juez.juzgar(entrada, "El usuario presento una queja sobre el servicio")
    assert generico.aprobado is False
    assert "suficiencia" in generico.criterio


def test_el_juez_aprueba_un_resumen_correcto(juez: JuezFake) -> None:
    """Contraparte del test anterior: no rechaza todo."""
    entrada = "El conductor venia hablando por celular y se paso dos semaforos en rojo."
    veredicto = juez.juzgar(entrada, "El conductor uso el celular y cruzo semaforos en rojo")
    assert veredicto.aprobado is True
