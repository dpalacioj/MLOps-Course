"""Tests del contrato de salida y del retry con feedback.

Estos tests son la razon por la que ``Proveedor`` es un parametro inyectable y no
un ``import``. Ninguno toca la red, ninguno necesita una API key, y todos son
deterministas: es lo que permite que corran en el CI de un fork.
"""

from __future__ import annotations

import pytest
from clasificador.clasificador import clasificar
from clasificador.esquema import (
    MAX_PALABRAS_RESUMEN,
    Categoria,
    ClasificacionQueja,
    ErrorDeContrato,
    extraer_json,
    parsear_clasificacion,
)
from clasificador.proveedor import ProveedorEco, ProveedorFake


# =============================================================================
# Validacion del contrato
# =============================================================================
def test_json_valido_produce_clasificacion() -> None:
    """El camino felíz: JSON bien formado y dentro del contrato."""
    salida = parsear_clasificacion(
        '{"categoria": "tarifa", "severidad": 3, '
        '"requiere_reembolso": true, "resumen": "Cobro doble"}'
    )
    assert isinstance(salida, ClasificacionQueja)
    assert salida.categoria == Categoria.TARIFA
    assert salida.severidad == 3
    assert salida.requiere_reembolso is True


def test_rechaza_json_malformado() -> None:
    """Una coma de mas es el fallo mas comun de un LLM pidiendo JSON."""
    with pytest.raises(ErrorDeContrato, match="JSON malformado"):
        parsear_clasificacion('{"categoria": "tarifa", "severidad": 3,}')


def test_rechaza_texto_sin_json() -> None:
    """El modelo respondio en prosa. No hay nada que parsear."""
    with pytest.raises(ErrorDeContrato, match="no contiene un objeto JSON"):
        parsear_clasificacion("Claro, con gusto clasifico esa queja para ti.")


def test_rechaza_categoria_fuera_del_enum() -> None:
    """El enum cerrado es lo que hace verificable la salida.

    El mensaje de error debe listar las categorias validas: ese texto es la
    entrada del retry con feedback, y sin el el modelo no puede corregir.
    """
    with pytest.raises(ErrorDeContrato) as exc:
        parsear_clasificacion(
            '{"categoria": "vehiculo", "severidad": 3, '
            '"requiere_reembolso": false, "resumen": "algo"}'
        )
    mensaje = str(exc.value)
    assert "categoria" in mensaje
    assert "tarifa" in mensaje, "el error debe listar los valores validos para el retry"


@pytest.mark.parametrize("severidad", [0, 6, 99, -1])
def test_rechaza_severidad_fuera_de_rango(severidad: int) -> None:
    """La severidad fuera de rango rompe la priorizacion aguas abajo."""
    with pytest.raises(ErrorDeContrato, match="severidad"):
        parsear_clasificacion(
            f'{{"categoria": "app", "severidad": {severidad}, '
            f'"requiere_reembolso": false, "resumen": "algo"}}'
        )


def test_rechaza_campo_extra() -> None:
    """``extra='forbid'``: un campo no declarado es sintoma de desincronizacion."""
    with pytest.raises(ErrorDeContrato, match="no esta en el contrato"):
        parsear_clasificacion(
            '{"categoria": "app", "severidad": 2, "requiere_reembolso": false, '
            '"resumen": "algo", "confianza": 0.9}'
        )


def test_rechaza_resumen_demasiado_largo() -> None:
    """El limite de palabras es un requisito de producto, no una preferencia."""
    largo = " ".join(["palabra"] * (MAX_PALABRAS_RESUMEN + 5))
    with pytest.raises(ErrorDeContrato, match="resumen"):
        parsear_clasificacion(
            f'{{"categoria": "otro", "severidad": 1, '
            f'"requiere_reembolso": false, "resumen": "{largo}"}}'
        )


def test_extrae_json_de_bloque_de_codigo() -> None:
    """El modelo obedece "devuelve JSON" y ademas lo formatea en markdown."""
    envuelto = '```json\n{"categoria": "app", "severidad": 2}\n```'
    assert extraer_json(envuelto) == '{"categoria": "app", "severidad": 2}'


def test_extrae_json_rodeado_de_prosa() -> None:
    """Prosa antes y despues del objeto: tambien frecuente."""
    crudo = 'Aqui esta:\n{"categoria": "app", "severidad": 2}\nEspero que ayude.'
    assert extraer_json(crudo) == '{"categoria": "app", "severidad": 2}'


# =============================================================================
# Retry con feedback
# =============================================================================
def test_retry_converge_tras_un_fallo(plantilla_v2) -> None:
    """El caso central: primer intento invalido, segundo valido.

    Verifica las tres cosas que hacen util al patron: que reintenta, que converge,
    y que el hecho de haber reintentado **queda registrado**. Sin lo tercero, el
    numero de reintentos no se puede monitorear y un prompt que hace trabajar el
    doble al modelo pasa desapercibido.
    """
    proveedor = ProveedorFake(fallos_iniciales=1)
    resultado = clasificar(
        "Me cobraron dos veces el viaje", proveedor=proveedor, plantilla=plantilla_v2
    )

    assert resultado.exito is True
    assert resultado.intentos == 2, "debio reintentar exactamente una vez"
    assert proveedor.llamadas == 2, "el proveedor debio recibir dos llamadas"
    assert len(resultado.errores) == 1, "el error del primer intento debe quedar registrado"
    assert resultado.clasificacion is not None


def test_retry_acumula_tokens_de_todos_los_intentos(plantilla_v2) -> None:
    """Contar solo el ultimo intento subestima el costo de los casos problematicos."""
    sin_fallo = clasificar(
        "Me cobraron dos veces", proveedor=ProveedorFake(), plantilla=plantilla_v2
    )
    con_fallo = clasificar(
        "Me cobraron dos veces",
        proveedor=ProveedorFake(fallos_iniciales=1),
        plantilla=plantilla_v2,
    )
    assert con_fallo.tokens_totales > sin_fallo.tokens_totales


def test_retry_se_agota_y_no_lanza(plantilla_v2) -> None:
    """Un caso irrecuperable no debe abortar el lote.

    Se devuelve ``exito=False`` en lugar de lanzar porque quien llama casi siempre
    esta procesando un lote (un eval de 36 casos, una cola de tickets), y un caso
    malo no puede tumbar los otros 35.
    """
    proveedor = ProveedorFake(fallos_iniciales=99)
    resultado = clasificar("cualquier queja", proveedor=proveedor, plantilla=plantilla_v2)

    assert resultado.exito is False
    assert resultado.clasificacion is None
    assert resultado.intentos == 2, "no debe reintentar mas alla de max_intentos"
    assert len(resultado.errores) == 2


def test_feedback_incluye_el_error_y_la_respuesta_anterior(plantilla_v2) -> None:
    """El turno de correccion debe llevar QUE se esta corrigiendo.

    Se usa ``ProveedorEco``, que devuelve la conversacion que recibio: es la forma
    de afirmar sobre el prompt realmente enviado sin espiar variables internas.
    Este es justamente el problema para el que existe ese proveedor.
    """
    eco = ProveedorEco()
    resultado = clasificar(
        "El taxi olia mal", proveedor=eco, plantilla=plantilla_v2, max_intentos=2
    )

    # El eco nunca cumple el contrato, asi que se agotan los intentos.
    assert resultado.exito is False
    conversacion = resultado.texto_crudo
    assert "[assistant]" in conversacion, "debe reenviarse la respuesta anterior del modelo"
    assert "no cumple el contrato" in conversacion, "debe incluirse el mensaje de error"
    assert "El taxi olia mal" in conversacion, "la queja original debe seguir en la conversacion"


def test_el_fake_clasifica_la_queja_no_el_mensaje_de_error(plantilla_v2) -> None:
    """Bug facil de escribir: usar el ULTIMO turno de usuario en un reintento.

    En un reintento el ultimo mensaje de usuario es el error de validacion. Si el
    proveedor lo toma como la queja, clasifica el mensaje de error.
    """
    proveedor = ProveedorFake(fallos_iniciales=1)
    resultado = clasificar(
        "El carro estaba sucio y olia a basura", proveedor=proveedor, plantilla=plantilla_v2
    )
    assert resultado.clasificacion is not None
    assert resultado.clasificacion.categoria == Categoria.LIMPIEZA


def test_max_intentos_invalido_es_error_de_programacion(plantilla_v2) -> None:
    """``max_intentos=0`` no tiene semantica: es un bug de quien llama."""
    with pytest.raises(ValueError, match="max_intentos"):
        clasificar("x", proveedor=ProveedorFake(), plantilla=plantilla_v2, max_intentos=0)
