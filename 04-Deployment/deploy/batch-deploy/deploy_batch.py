"""
Script para crear y servir deployment automático de batch predictions.
Modo demo/clase: cada 4 minutos con 1000 viajes.
Para produccion real, cambiar cron a "0 * * * *" (cada hora).
"""

import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.prefect_flows import scheduled_batch_flow

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

if __name__ == "__main__":
    logging.info("="*60)
    logging.info("DEPLOYMENT AUTOMÁTICO - BATCH PREDICTIONS")
    logging.info("="*60)
    logging.info("Configuración:")
    logging.info("  Nombre: batch-prediction-demo")
    logging.info("  Frecuencia: Cada 4 minutos (*/4 * * * *) - modo clase")
    logging.info("  Viajes por batch: 1000")
    logging.info("="*60)
    logging.info("Iniciando deployment...")
    logging.info("Presiona Ctrl+C para detener")
    logging.info("="*60)

    scheduled_batch_flow.serve(
        name="batch-prediction-demo",
        cron="*/4 * * * *",  # Cada 4 minutos (modo clase)
        description="Predicciones batch cada 4 minutos (demo)"
    )
