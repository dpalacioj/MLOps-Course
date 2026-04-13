"""
Transformer: Validacion de calidad de datos.

Este bloque es el equivalente a validate_data() del pipeline Prefect.
En Mage, un @transformer recibe datos del bloque anterior y retorna datos transformados.
"""

import pandas as pd

if 'transformer' not in globals():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import MIN_RECORDS, NULL_THRESHOLD


@transformer
def validate_data(df: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
    """
    Valida la calidad de los datos antes de procesarlos.

    Verificaciones:
    - Volumen minimo de registros
    - Porcentaje de valores nulos

    Args:
        df: DataFrame con datos de taxi.

    Returns:
        El mismo DataFrame (solo emite warnings, no filtra).
    """
    # Verificar volumen
    if len(df) < MIN_RECORDS:
        print(f"ADVERTENCIA: Volumen bajo: {len(df)} filas "
              f"(recomendado: {MIN_RECORDS})")

    # Verificar nulos
    null_pct = df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100
    if null_pct > NULL_THRESHOLD:
        print(f"ADVERTENCIA: Alto porcentaje de nulos: {null_pct:.2f}%")

    print(f"Validacion completada: {len(df):,} filas, {null_pct:.2f}% nulos")

    return df


@test
def test_output(output, *args) -> None:
    """Verifica que la validacion no elimino registros."""
    assert output is not None, 'El output es None'
    assert len(output) > 0, 'El DataFrame esta vacio despues de validacion'
    print(f"Test OK: {len(output):,} registros validados")
