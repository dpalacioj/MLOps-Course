# =============================================================================
# Makefile — interfaz unica del proyecto
# =============================================================================
# Regla de oro: el CI corre EXACTAMENTE estos targets. Asi "pasa en mi maquina"
# y "pasa en CI" significan lo mismo, y cuando divergen se nota de inmediato.
#
# Regla numero dos: `make smoke` tiene que ser UN comando que verifique el
# entorno completo. Es lo primero que va a correr quien te haga peer review, y
# si no funciona, tu nota de reproducibilidad ya esta decidida.
#
#   make            muestra esta ayuda
#   make setup      instala todo y configura los hooks
#   make smoke      verifica que el entorno quedo bien   <-- empieza aqui
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
UV := uv
PY := $(UV) run
COMPOSE := docker compose

.PHONY: help setup smoke data train promote drift serve batch model-card \
        test test-fast lint format typecheck check up down logs clean clean-all

# =============================================================================
help: ## Muestra los targets disponibles
	@echo ""
	@echo "  miproyecto — targets disponibles"
	@echo "  --------------------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Entorno
# =============================================================================
setup: ## Instala dependencias, genera uv.lock y configura pre-commit
	$(UV) sync --group dev
	$(PY) pre-commit install --install-hooks
	@echo ""
	@echo "IMPORTANTE: commitea uv.lock. Sin el, el CI (`uv sync --locked`) falla"
	@echo "y nadie puede reproducir tus resultados."
	@echo ""
	@echo "Listo. Ahora corre: make smoke"

smoke: ## Verifica el entorno en un comando (esto corre tu revisor)
	$(PY) python scripts/smoke_test.py

# =============================================================================
# Datos y modelo
# =============================================================================
data: ## Descarga y prepara las particiones declaradas en config.py
	$(PY) python -c "from miproyecto.data import loaders; from miproyecto import config; \
	  loaders.cachear(loaders.preparar_particiones(config.PARTICIONES_TRAIN), 'train')"

train: ## Entrena el candidato y lo registra en MLflow con alias @candidate
	$(PY) python -m miproyecto.models.train

promote: ## Gate de promocion: candidato vs @champion en el holdout fijo
	$(PY) python -m miproyecto.models.promote

drift: ## Reporte de drift: referencia vs produccion simulada
	$(PY) python -m miproyecto.monitoring.check_drift

model-card: ## Genera docs/model-card.md desde el modelo registrado
	$(PY) python scripts/model_card.py

serve: ## Levanta la API en http://127.0.0.1:8000/docs
	$(PY) uvicorn miproyecto.api.main:app --reload --host 127.0.0.1 --port 8000

# =============================================================================
# Calidad — el CI corre exactamente esto
# =============================================================================
test: ## Corre todos los tests
	$(PY) pytest

test-fast: ## Solo los tests que no requieren red ni servicios
	$(PY) pytest -m "not slow and not integration"

lint: ## Revisa estilo y errores con ruff
	$(PY) ruff check .

format: ## Formatea el codigo con ruff
	$(PY) ruff format .

typecheck: ## Verifica tipos con mypy
	$(PY) mypy

check: lint typecheck test-fast ## Todo lo que el CI verifica, en local

# =============================================================================
# Servicios locales
# =============================================================================
up: ## Levanta MLflow y la API con docker compose
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  MLflow  http://127.0.0.1:5001"
	@echo "  API     http://127.0.0.1:8000/docs"

down: ## Detiene el stack
	$(COMPOSE) down

logs: ## Sigue los logs del stack
	$(COMPOSE) logs -f

# =============================================================================
# Limpieza
# =============================================================================
clean: ## Borra caches y reportes temporales
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	rm -rf reports/*.html

clean-all: clean ## Borra tambien datos, modelos y mlruns (destructivo)
	rm -rf data/raw data/processed mlruns mlartifacts mlflow.db models
