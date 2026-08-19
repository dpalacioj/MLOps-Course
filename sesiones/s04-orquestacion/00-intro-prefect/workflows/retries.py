"""Reintentos con backoff, sin depender de servicios de terceros.

Bug corregido: la version anterior de este archivo llamaba a
`https://tools-httpstatus.pickup-services.com/{200|500}` para simular fallos.
Depender de un endpoint de terceros para *ensenar* resiliencia tiene dos
problemas: si el servicio esta caido la demo no funciona (y el instructor queda
explicando por que falla lo que no deberia fallar), y el fallo es aleatorio, asi
que la salida no es reproducible en clase.

Aqui el fallo es **local y determinista**: la task falla exactamente las primeras
`fallos_simulados` veces y despues funciona. El numero de intento se lee de
`prefect.runtime.task_run.run_count`, que Prefect incrementa en cada reintento.

Sobre el backoff. `retry_delay_seconds` acepta:

- un numero: la misma espera en todos los intentos;
- una **lista**: una espera por intento (backoff explicito);
- combinado con `retry_jitter_factor`, desincroniza reintentos simultaneos, que
  es lo que evita el thundering herd cuando fallan cien tasks a la vez.

Cuando el fallo es de red, esperar 2 segundos y volver a intentar agrega carga
justo cuando el otro extremo esta peor, y los tres intentos se agotan dentro de
la misma ventana de degradacion: es casi equivalente a no reintentar.
"""

from prefect import flow, task
from prefect.runtime import task_run


@task(retries=3, retry_delay_seconds=[1, 2, 4], retry_jitter_factor=0.2)
def descargar_particion_inestable(fallos_simulados: int = 2) -> str:
    """Simula una descarga que falla las primeras veces y luego funciona."""
    intento = task_run.run_count
    print(f"Intento {intento}")
    if intento <= fallos_simulados:
        # Un ConnectionError, no un Exception genarico: el tipo de la excepcion
        # es informacion para quien lee el log a las 3 a.m.
        raise ConnectionError(f"fallo de red simulado en el intento {intento}")
    return f"descarga completada en el intento {intento}"


@flow(log_prints=True)
def demo_reintentos(fallos_simulados: int = 2) -> str:
    """Ejecuta la task inestable y devuelve su resultado."""
    return descargar_particion_inestable(fallos_simulados)


if __name__ == "__main__":
    print(demo_reintentos())

    # Para ver la task agotar los reintentos y que el flow termine en Failed:
    #   demo_reintentos(fallos_simulados=9)
    # En Prefect 3 el estado final del flow se deriva del valor de retorno o de
    # la excepcion que se propague, no de los estados de las tasks.
