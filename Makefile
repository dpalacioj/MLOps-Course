# =============================================================================
# Makefile — Curso MLOps
# =============================================================================
# Interfaz unica del repositorio. El CI usa exactamente estos mismos targets,
# de modo que "pasa en mi maquina" y "pasa en CI" significan lo mismo.
#
#   make            muestra esta ayuda
#   make setup      instala todo y configura los hooks
#   make smoke      verifica que el entorno quedo bien  <-- empieza aqui
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
UV := uv
PY := $(UV) run
COMPOSE := docker compose

.PHONY: help setup smoke data train hpo promote serve batch drift model-card \
        test test-fast test-llmops evals-llm comparar-prompts \
        lint format typecheck check up down logs clean clean-all \
        mlflow prefect notebooks

# =============================================================================
help: ## Muestra los targets disponibles
	@echo ""
	@echo "  Curso MLOps — targets disponibles"
	@echo "  ---------------------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Entorno
# =============================================================================
setup: ## Instala dependencias, hooks de git y pre-commit
	$(UV) sync --group dev
	@# core.hooksPath NO se configura. Git admite un solo lugar para los hooks, y
	@# apuntarlo a .githooks/ hacia que `pre-commit install` se negara a instalarse
	@# ("Cowardly refusing to install hooks with core.hooksPath set"), dejando el
	@# repositorio sin ruff, gitleaks, nbstripout ni los hooks propios del curso.
	@# pre-commit es ahora el unico sistema: cubre pre-commit, commit-msg y pre-push.
	@git config --get core.hooksPath >/dev/null 2>&1 \
	  && (echo "Limpiando core.hooksPath heredado..."; git config --unset-all core.hooksPath) \
	  || true
	$(PY) pre-commit install --install-hooks
	@command -v git-lfs >/dev/null 2>&1 \
	  && (git lfs install && git lfs pull) \
	  || echo "AVISO: git-lfs no esta instalado. Los diagramas .png no se veran."
	@echo ""
	@echo "Listo. Ahora corre: make smoke"

smoke: ## Verifica el entorno (Python, deps, LFS, puertos, contratos)
	$(PY) python scripts/smoke_test.py

# =============================================================================
# Datos y modelo (caso guia: NYC Green Taxi, particiones fijas)
# =============================================================================
data: ## Descarga y prepara las particiones del caso guia
	$(PY) taxi data

train: ## Entrena el baseline y lo registra en MLflow
	$(PY) taxi train

hpo: ## Busqueda de hiperparametros con Optuna (runs anidados)
	$(PY) taxi train --hpo --trials 20

promote: ## Ejecuta el gate de promocion (candidato vs @champion)
	$(PY) taxi promote

model-card: ## Genera docs/model-card.md desde el modelo registrado
	$(PY) taxi model-card

drift: ## Reporte de drift: referencia vs produccion simulada
	$(PY) taxi drift

serve: ## Levanta la API de inferencia en http://127.0.0.1:8000/docs
	$(PY) uvicorn taxi.api.main:app --reload --port 8000

batch: ## Corre el pipeline batch de predicciones
	$(PY) python -m taxi.flows.batch

# =============================================================================
# Calidad — el CI corre exactamente esto
# =============================================================================
test: ## Corre todos los tests
	$(PY) pytest

test-fast: ## Corre solo los tests que no requieren red ni servicios
	$(PY) pytest -m "not slow and not integration"

test-llmops: ## Corre solo los tests de la sesion 8 (sin red, sin API key)
	$(PY) pytest sesiones/s08-llmops/tests

evals-llm: ## Eval del clasificador de quejas (S08). Exit != 0 si baja del umbral.
	PYTHONPATH=sesiones/s08-llmops/src LLMOPS_PROVEEDOR=fake LLMOPS_TRACING=off \
	  $(PY) python -m clasificador.evaluar --sin-mlflow

comparar-prompts: ## Compara las dos versiones del prompt de la sesion 8
	PYTHONPATH=sesiones/s08-llmops/src LLMOPS_TRACING=off \
	  $(PY) python -m clasificador.comparar_prompts

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
up: ## Levanta el stack completo (MLflow, MinIO, Postgres, API, Grafana)
	$(COMPOSE) up -d
	@echo ""
	@echo "  MLflow      http://127.0.0.1:5001"
	@echo "  API         http://127.0.0.1:8000/docs"
	@echo "  MinIO       http://127.0.0.1:9001  (minioadmin / minioadmin)"
	@echo "  Prometheus  http://127.0.0.1:9090"
	@echo "  Grafana     http://127.0.0.1:3000  (admin / admin)"

down: ## Detiene el stack
	$(COMPOSE) down

logs: ## Sigue los logs del stack
	$(COMPOSE) logs -f

mlflow: ## MLflow server local sin Docker (SQLite + artifacts locales)
	$(PY) mlflow server \
	  --backend-store-uri sqlite:///mlflow.db \
	  --default-artifact-root ./mlartifacts \
	  --host 127.0.0.1 --port 5001

prefect: ## Prefect server local sin Docker
	$(PY) prefect server start

# =============================================================================
# Limpieza
# =============================================================================
clean: ## Borra caches y artefactos temporales
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	rm -rf reports/*.html

clean-all: clean ## Borra tambien datos, modelos y mlruns (destructivo)
	rm -rf data/raw data/processed mlruns mlartifacts mlflow.db models
