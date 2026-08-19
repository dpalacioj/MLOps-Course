## Datos, Variables de Entorno y Secretos

### Variables de entorno locales con .env

- Nunca comitees tu archivo `.env`. La plantilla `.gitignore` proporcionada lo excluye.

### Cargar variables en Python

Instala `python-dotenv` (elige tu herramienta):

```bash
uv add python-dotenv   # or: poetry add python-dotenv
```

Uso:

```python
from dotenv import load_dotenv
import os

load_dotenv()  # reads .env

db_url = os.getenv("DATABASE_URL")
```

### Secretos en CI (GitHub Actions)

- Guarda los valores sensibles en GitHub → Settings → Secrets and variables → Actions.
- Haz referencia a ellos en los workflows como `${{ secrets.MY_SECRET }}`.
- No imprimas secretos en los logs; pásalos como variables de entorno a los pasos o herramientas.

### Archivos de datos

- Mantén los datos grandes fuera de Git; usa registros de datos o almacenamiento de objetos cuando sea posible.
- Si se necesitan pequeños conjuntos de datos de ejemplo para tests, inclúyelos en una carpeta `data/` con licencia clara.
