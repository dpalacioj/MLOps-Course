"""Tests de los scorers deterministas.

Un scorer con un bug es peor que no tener scorer: produce un numero que el equipo
usa para decidir. Estos tests verifican que cada scorer puntua **bien** los casos
correctos y **mal** los incorrectos, que es lo minimo para poder creerle.
"""

from __future__ import annotations

import pytest
from clasificador.clasificador import ResultadoClasificacion
from clasificador.datos import CasoEval
from clasificador.esquema import ClasificacionQueja
from clasificador.scorers import deterministas as det


def _resultado(
    *,
    categoria: str = "tarifa",
    severidad: int = 3,
    reembolso: bool = True,
    resumen: str = "Cobro doble sin explicacion",
    exito: bool = True,
    intentos: int = 1,
) -> ResultadoClasificacion:
    """Construye un ``ResultadoClasificacion`` para los tests."""
    clasificacion = (
        ClasificacionQueja(
            categoria=categoria,  # type: ignore[arg-type]
            severidad=severidad,
            requiere_reembolso=reembolso,
            resumen=resumen,
        )
        if exito
        else None
    )
    return ResultadoClasificacion(
        clasificacion=clasificacion,
        exito=exito,
        intentos=intentos,
        tokens_entrada=100,
        tokens_salida=20,
        modelo="fake-reglas-v1",
        proveedor="fake",
        etiqueta_prompt="v2",
        huella_prompt="abc123",
    )


def _caso(*, categoria: str = "tarifa", severidad: int = 3, reembolso: bool = True) -> CasoEval:
    return CasoEval(
        id="t01",
        entrada="Me cobraron dos veces",
        esperado={
            "categoria": categoria,
            "severidad": severidad,
            "requiere_reembolso": reembolso,
        },
    )


# =============================================================================
# Scorers de contrato
# =============================================================================
def test_json_valido_puntua_bien_y_mal() -> None:
    """El scorer mas importante, en sus dos direcciones."""
    assert det.json_valido(_resultado()).valor == 1.0
    fallido = det.json_valido(_resultado(exito=False))
    assert fallido.valor == 0.0
    assert fallido.motivo, "un 0.0 sin motivo obliga a reproducir el caso a mano"


def test_sin_reintentos_distingue_el_primer_intento() -> None:
    """Un sistema que siempre acierta al segundo intento tiene el doble de costo."""
    assert det.sin_reintentos(_resultado(intentos=1)).valor == 1.0
    assert det.sin_reintentos(_resultado(intentos=2)).valor == 0.0


def test_resumen_dentro_del_limite_aprueba_lo_corto() -> None:
    """El limite de 20 palabras es un requisito de la UI de soporte."""
    puntaje = det.resumen_dentro_del_limite(_resultado(resumen="Cobro doble"))
    assert puntaje.valor == 1.0
    assert "2 palabras" in puntaje.motivo


def test_resumen_dentro_del_limite_detecta_lo_largo() -> None:
    """El scorer debe funcionar aunque la salida no haya pasado por el validador.

    Se usa ``model_construct``, que **omite** la validacion de Pydantic, para
    simular exactamente el escenario que justifica que este scorer exista: alguien
    relaja el esquema, o aparece un camino de codigo que no pasa por
    ``parsear_clasificacion``. Si el scorer solo funcionara sobre objetos ya
    validados seria decorativo.
    """
    sin_validar = ClasificacionQueja.model_construct(
        categoria="otro",
        severidad=1,
        requiere_reembolso=False,
        resumen=" ".join(["palabra"] * 25),
    )
    resultado = _resultado()
    resultado.clasificacion = sin_validar

    puntaje = det.resumen_dentro_del_limite(resultado)
    assert puntaje.valor == 0.0
    assert "25 palabras" in puntaje.motivo


def test_resumen_vacio_no_pasa() -> None:
    """Un resumen vacio cumple el limite numericamente y no sirve para nada."""
    resultado = _resultado()
    resultado.clasificacion = ClasificacionQueja.model_construct(
        categoria="otro", severidad=1, requiere_reembolso=False, resumen="   "
    )
    assert det.resumen_dentro_del_limite(resultado).valor == 0.0


def test_severidad_en_rango() -> None:
    """Dentro del contrato Pydantic ya no puede salirse, y el scorer lo documenta."""
    assert det.severidad_en_rango(_resultado(severidad=1)).valor == 1.0
    assert det.severidad_en_rango(_resultado(severidad=5)).valor == 1.0
    assert det.severidad_en_rango(_resultado(exito=False)).valor == 0.0


@pytest.mark.parametrize(
    "resumen,esperado_limpio",
    [
        ("Cobro doble sin explicacion", True),
        ("El usuario escribio a juan.perez@example.org", False),
        ("Contactar al 3001234567 del usuario", False),
        ("Vehiculo con placa ABC123 sucio", False),
        ("Cargo a la tarjeta terminada en 4321", False),
        ("Destino en la carrera 43 #12-05", False),
        ("Cobro de 45 mil frente a 28 mil estimados", True),
    ],
)
def test_salida_sin_pii(resumen: str, esperado_limpio: bool) -> None:
    """PII se mide sobre la SALIDA, no sobre la entrada.

    El usuario puede escribir su telefono en la queja y esta en su derecho. El
    problema es que el sistema lo copie al resumen, porque desde ahi se propaga a
    los tickets, los logs y las trazas.

    Los dos ultimos casos delimitan el scorer: un monto ("45 mil") no es PII y una
    tarjeta parcial si, aunque venga de la queja original.
    """
    puntaje = det.salida_sin_pii(_resultado(resumen=resumen))
    assert puntaje.aprobado is esperado_limpio, puntaje.motivo


def test_deteccion_de_pii_reporta_el_tipo() -> None:
    """El tipo de PII encontrado es lo accionable, no solo el booleano."""
    hallazgos = det.detectar_pii("escribir a a@b.co o llamar al 3109876543")
    assert "correo" in hallazgos
    assert "telefono" in hallazgos


# =============================================================================
# Scorers de exactitud
# =============================================================================
def test_categoria_correcta_en_ambas_direcciones() -> None:
    """La metrica que solo existe porque alguien etiqueto el dataset a mano."""
    caso = _caso(categoria="tarifa")
    assert det.categoria_correcta(_resultado(categoria="tarifa"), caso).valor == 1.0

    fallido = det.categoria_correcta(_resultado(categoria="app"), caso)
    assert fallido.valor == 0.0
    assert "tarifa" in fallido.motivo and "app" in fallido.motivo


def test_severidad_exacta_vs_con_tolerancia() -> None:
    """Las dos metricas se reportan juntas y miden cosas distintas.

    Con etiqueta 3 y prediccion 4: la exacta falla y la tolerante pasa. Publicar
    solo la tolerante infla el numero; publicar solo la exacta castiga al modelo
    por un desacuerdo que dos anotadores humanos tambien tienen.
    """
    caso = _caso(severidad=3)
    resultado = _resultado(severidad=4)
    assert det.severidad_exacta(resultado, caso).valor == 0.0
    assert det.severidad_con_tolerancia(resultado, caso).valor == 1.0

    lejano = _resultado(severidad=1)
    assert det.severidad_con_tolerancia(lejano, caso).valor == 0.0


def test_reembolso_correcto() -> None:
    """El campo con consecuencia economica directa."""
    caso = _caso(reembolso=True)
    assert det.reembolso_correcto(_resultado(reembolso=True), caso).valor == 1.0
    assert det.reembolso_correcto(_resultado(reembolso=False), caso).valor == 0.0


# =============================================================================
# Orquestacion
# =============================================================================
def test_puntuar_sin_caso_omite_los_de_exactitud() -> None:
    """Sin etiquetas solo corren los de contrato: es el modo de PRODUCCION.

    Esa distincion es la que permite monitorear calidad sobre trafico real, donde
    nunca hay verdad de terreno.
    """
    nombres_sin_caso = {p.nombre for p in det.puntuar(_resultado())}
    assert nombres_sin_caso == set(det.SCORERS_DE_CONTRATO)

    nombres_con_caso = {p.nombre for p in det.puntuar(_resultado(), _caso())}
    assert nombres_con_caso == set(det.TODOS_LOS_SCORERS)


def test_agregar_promedia_por_scorer() -> None:
    """La media de un scorer binario es la fraccion de casos que pasaron."""
    caso = _caso(categoria="tarifa")
    puntajes = [
        det.puntuar(_resultado(categoria="tarifa"), caso),
        det.puntuar(_resultado(categoria="app"), caso),
    ]
    agregado = det.agregar(puntajes)
    assert agregado["categoria_correcta"] == 0.5
    assert agregado["json_valido"] == 1.0


def test_no_hay_metrica_global_unica() -> None:
    """Mezclar exactitud con ausencia de PII en un numero oculta regresiones.

    Este test protege una decision de diseno: ``agregar`` devuelve un valor por
    scorer y ninguna media de medias. Si alguien agrega una clave tipo 'total' o
    'calidad', este test falla y la discusion ocurre en el PR.
    """
    agregado = det.agregar([det.puntuar(_resultado(), _caso())])
    assert set(agregado) == set(det.TODOS_LOS_SCORERS)
    for prohibido in ("total", "global", "calidad", "score"):
        assert prohibido not in agregado
