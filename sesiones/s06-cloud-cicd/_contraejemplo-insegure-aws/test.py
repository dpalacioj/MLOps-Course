# CONTRAEJEMPLO — NO COPIAR
#
# Este archivo se conserva a proposito como material didactico de la sesion 6.
# NO es un ejemplo a seguir: tiene al menos cinco defectos de seguridad y de
# diseno documentados en `README.md` de esta misma carpeta.
#
# El linter lo excluye (ver `extend-exclude` en el pyproject.toml de la raiz) para
# que sus errores no se mezclen con los del codigo real del curso.
#
import requests

ride = {
    "PULocationID": 10,
    "DOLocationID": 50,
    "trip_distance": 40
}

url = 'http://localhost:9696/predict'
response = requests.post(url, json=ride)
print(response.json())
