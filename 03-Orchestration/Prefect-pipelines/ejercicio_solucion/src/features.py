"""
Preprocesamiento de features.
Escalamos las variables numericas para que tengan media 0 y desviacion estandar 1.
"""

from sklearn.preprocessing import StandardScaler
from prefect import task, get_run_logger


@task(name="escalar_features", description="Escala features con StandardScaler")
def escalar_features(X_train, X_test):
    """Aplica StandardScaler: fit en train, transform en ambos."""
    logger = get_run_logger()

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logger.info(f"Features escaladas: {X_train_scaled.shape[1]} columnas")
    return X_train_scaled, X_test_scaled, scaler
