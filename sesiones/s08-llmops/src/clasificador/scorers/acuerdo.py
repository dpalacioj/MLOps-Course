"""Acuerdo juez-humano: porcentaje de acuerdo y kappa de Cohen.

Problema que resuelve
---------------------
> **Un juez sin calibrar contra una muestra etiquetada por humanos no es una
> metrica: es una opinion con API.**

Esa frase es la regla no negociable de la sesion. Este modulo es lo que la
convierte en un numero, y sin ese numero el resultado del juez no se reporta.

El fallo que evita es concreto y frecuente: se escribe un juez de LLM, se corre
sobre 200 casos, sale 0.87 y ese 0.87 acaba en un slide. Nadie verifico que el
juez coincida con lo que una persona habria dicho. Si el juez aprueba casi todo
—el sesgo mas comun en un juez sin rubrica— el 0.87 no mide calidad: mide la
propension del juez a aprobar.

Por que kappa y no solo el porcentaje
-------------------------------------
Si el 85% de los resumenes son buenos, un juez que aprueba TODO saca 85% de
acuerdo. Suena bien y no distingue nada. Kappa descuenta el acuerdo esperado por
azar y en ese caso da exactamente 0.

Es el mismo argumento por el que en clasificacion desbalanceada no se reporta
accuracy sola. La diferencia es que aqui el "modelo" es el juez y la "etiqueta"
es el criterio humano.

Limitaciones que hay que decir en voz alta
------------------------------------------
- **La paradoja de kappa**: con marginales muy desbalanceados kappa puede dar
  bajo aunque el acuerdo observado sea alto. Por eso se reportan los dos numeros
  y la matriz de confusion, no uno solo.
- Kappa de Cohen es para **dos** evaluadores y categorias nominales. Para tres o
  mas se usa kappa de Fleiss; para escalas ordinales, kappa ponderado.
- El corte de 0.40/0.60 viene de la escala de Landis y Koch (1977). Es una
  **convencion**, no un resultado. Lo que importa no es el corte exacto sino que
  este declarado antes de mirar el resultado.

Se implementa a mano (unas 20 lineas) en lugar de traer ``sklearn.metrics.
cohen_kappa_score``. Razon didactica, y es la principal: kappa se cita mucho y se
entiende poco. Verlo como "acuerdo observado menos acuerdo esperado, normalizado"
hace evidente de donde sale el 0 y de donde sale el 1. ``sklearn`` esta en el
entorno del curso y en produccion es lo que se usaria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Cortes de interpretacion de kappa (Landis y Koch, 1977). Declarados aqui,
#: antes de medir, para no elegirlos despues de ver el resultado.
KAPPA_MINIMO_REPORTABLE: Final[float] = 0.40
KAPPA_MINIMO_PARA_GATE: Final[float] = 0.60

#: Minimo de casos etiquetados a mano para que el numero signifique algo. Con
#: menos de 10, el intervalo de confianza de kappa es tan ancho que el valor
#: puntual no informa. 10 es un piso practico para una sesion de clase, no una
#: recomendacion para produccion: ahi se usan 50-200 y se reporta el intervalo.
MINIMO_CASOS_CALIBRACION: Final[int] = 10


@dataclass(frozen=True)
class Acuerdo:
    """Resultado de la calibracion juez vs humano."""

    n: int
    acuerdos: int
    #: Matriz 2x2 sobre las etiquetas 'aprobado'/'rechazado'.
    juez_si_humano_si: int
    juez_si_humano_no: int
    juez_no_humano_si: int
    juez_no_humano_no: int
    porcentaje_acuerdo: float
    kappa: float

    @property
    def interpretacion(self) -> str:
        """Lectura del kappa segun los cortes declarados arriba."""
        if self.n < MINIMO_CASOS_CALIBRACION:
            return f"insuficiente: {self.n} casos, se necesitan {MINIMO_CASOS_CALIBRACION}"
        if self.kappa < KAPPA_MINIMO_REPORTABLE:
            return "pobre: el resultado del juez NO se debe reportar"
        if self.kappa < KAPPA_MINIMO_PARA_GATE:
            return "moderado: reportar SIEMPRE junto al kappa, no usar como gate"
        return "sustancial: se puede usar como gate, con el kappa en el reporte"

    @property
    def utilizable_como_gate(self) -> bool:
        """Si el juez esta lo bastante calibrado para bloquear un despliegue."""
        return self.n >= MINIMO_CASOS_CALIBRACION and self.kappa >= KAPPA_MINIMO_PARA_GATE

    @property
    def sesgo_del_juez(self) -> str:
        """Describe la direccion del desacuerdo, que es lo accionable.

        Saber que kappa es 0.3 no dice como arreglarlo. Saber que el juez aprueba
        casos que el humano rechaza indica que la rubrica es demasiado permisiva o
        que el juez no la esta aplicando; el desacuerdo inverso indica que es
        demasiado estricta. Son dos arreglos distintos.
        """
        falsos_aprobados = self.juez_si_humano_no
        falsos_rechazados = self.juez_no_humano_si
        if falsos_aprobados == falsos_rechazados == 0:
            return "sin desacuerdos"
        if falsos_aprobados > falsos_rechazados:
            return (
                f"el juez es mas permisivo que el humano "
                f"({falsos_aprobados} aprobo lo que el humano rechazo)"
            )
        if falsos_rechazados > falsos_aprobados:
            return (
                f"el juez es mas estricto que el humano "
                f"({falsos_rechazados} rechazo lo que el humano aprobo)"
            )
        return f"desacuerdo simetrico ({falsos_aprobados} en cada direccion)"

    def como_dict(self) -> dict[str, float | int | str]:
        return {
            "n": self.n,
            "acuerdos": self.acuerdos,
            "porcentaje_acuerdo": round(self.porcentaje_acuerdo, 4),
            "kappa": round(self.kappa, 4),
            "interpretacion": self.interpretacion,
            "sesgo_del_juez": self.sesgo_del_juez,
            "juez_si_humano_si": self.juez_si_humano_si,
            "juez_si_humano_no": self.juez_si_humano_no,
            "juez_no_humano_si": self.juez_no_humano_si,
            "juez_no_humano_no": self.juez_no_humano_no,
        }


def cohen_kappa(veredictos_juez: list[bool], veredictos_humano: list[bool]) -> float:
    """Kappa de Cohen para dos evaluadores y etiquetas binarias.

    Formula::

        kappa = (Po - Pe) / (1 - Pe)

    donde ``Po`` es el acuerdo observado y ``Pe`` el acuerdo esperado si ambos
    evaluadores etiquetaran al azar respetando sus propias frecuencias
    marginales.

    Casos degenerados, que son los que confunden y por eso se tratan explicito:

    - **Acuerdo perfecto**: ``Po = 1`` y ``Pe < 1`` -> kappa 1.0.
    - **Ambos etiquetan todo igual** (los dos aprueban los 12 casos): ``Po = 1``
      pero tambien ``Pe = 1``, y la formula da 0/0. Se devuelve **1.0** porque el
      acuerdo observado es total. Es una convencion discutible —hay implementaciones
      que devuelven NaN— y lo importante es saber que en ese escenario kappa **no
      informa**: sin variacion en las etiquetas no hay nada que descontar por
      azar. La lectura correcta no es "kappa perfecto" sino "el conjunto de
      calibracion no tiene casos negativos y hay que agregarlos".
    - **Desacuerdo total** con marginales balanceados -> kappa negativo, peor que
      el azar.

    Raises:
        ValueError: si las listas tienen longitudes distintas o estan vacias.
    """
    if len(veredictos_juez) != len(veredictos_humano):
        raise ValueError(
            f"las listas deben tener el mismo largo: {len(veredictos_juez)} vs "
            f"{len(veredictos_humano)}"
        )
    n = len(veredictos_juez)
    if n == 0:
        raise ValueError("no se puede calcular kappa sobre cero casos")

    acuerdo_observado = (
        sum(j == h for j, h in zip(veredictos_juez, veredictos_humano, strict=True)) / n
    )

    # Marginales: la propension de cada evaluador a decir 'aprobado'.
    p_juez_si = sum(veredictos_juez) / n
    p_humano_si = sum(veredictos_humano) / n
    acuerdo_esperado = p_juez_si * p_humano_si + (1 - p_juez_si) * (1 - p_humano_si)

    if acuerdo_esperado >= 1.0:
        # Ambos evaluadores usaron una sola etiqueta. Ver el docstring.
        return 1.0 if acuerdo_observado >= 1.0 else 0.0
    return (acuerdo_observado - acuerdo_esperado) / (1 - acuerdo_esperado)


def medir_acuerdo(veredictos_juez: list[bool], veredictos_humano: list[bool]) -> Acuerdo:
    """Calcula el acuerdo completo: porcentaje, kappa y matriz de confusion.

    Args:
        veredictos_juez: ``True`` = el juez aprobo.
        veredictos_humano: ``True`` = el humano aprobo. Es la referencia.

    Returns:
        ``Acuerdo``, con la interpretacion y la direccion del sesgo.
    """
    if len(veredictos_juez) != len(veredictos_humano):
        raise ValueError("las listas deben tener el mismo largo")
    n = len(veredictos_juez)
    if n == 0:
        raise ValueError("no se puede medir acuerdo sobre cero casos")

    matriz = {(True, True): 0, (True, False): 0, (False, True): 0, (False, False): 0}
    for juez, humano in zip(veredictos_juez, veredictos_humano, strict=True):
        matriz[(juez, humano)] += 1

    acuerdos = matriz[(True, True)] + matriz[(False, False)]
    return Acuerdo(
        n=n,
        acuerdos=acuerdos,
        juez_si_humano_si=matriz[(True, True)],
        juez_si_humano_no=matriz[(True, False)],
        juez_no_humano_si=matriz[(False, True)],
        juez_no_humano_no=matriz[(False, False)],
        porcentaje_acuerdo=acuerdos / n,
        kappa=cohen_kappa(veredictos_juez, veredictos_humano),
    )
