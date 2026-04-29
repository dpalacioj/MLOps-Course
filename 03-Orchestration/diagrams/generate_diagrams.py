#!/usr/bin/env python
"""
Generador de diagramas educativos para el modulo de Orquestacion.
Secuencia pedagogica: desde el problema hasta arquitectura de produccion.

Uso:
    python generate_diagrams.py

Genera 12 PNGs en este directorio.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, ArrowStyle
import numpy as np

# ==============================================================================
# Estilos globales
# ==============================================================================
COLORS = {
    'bg': '#FAFBFC',
    'prefect_blue': '#1A73E8',
    'prefect_dark': '#0D47A1',
    'success': '#2E7D32',
    'error': '#C62828',
    'warning': '#F57F17',
    'orange': '#E65100',
    'purple': '#6A1B9A',
    'teal': '#00695C',
    'gray': '#546E7A',
    'light_gray': '#ECEFF1',
    'light_blue': '#E3F2FD',
    'light_green': '#E8F5E9',
    'light_red': '#FFEBEE',
    'light_orange': '#FFF3E0',
    'light_purple': '#F3E5F5',
    'light_teal': '#E0F2F1',
    'white': '#FFFFFF',
    'black': '#212121',
    'mage_purple': '#7B1FA2',
    'airflow_teal': '#017CEE',
    'dagster_blue': '#4F43AF',
}

def setup_figure(figsize=(14, 8), title=""):
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')
    if title:
        ax.text(5, 9.5, title, fontsize=20, fontweight='bold',
                ha='center', va='center', color=COLORS['prefect_dark'],
                fontfamily='sans-serif')
    return fig, ax


def draw_box(ax, x, y, w, h, text, color, text_color='white', fontsize=11,
             alpha=1.0, border_color=None, style='round,pad=0.1', text_lines=None):
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                          boxstyle=style,
                          facecolor=color, edgecolor=border_color or color,
                          linewidth=2, alpha=alpha, zorder=2)
    ax.add_patch(box)
    if text_lines:
        line_height = fontsize * 0.015
        start_y = y + (len(text_lines) - 1) * line_height / 2
        for i, line in enumerate(text_lines):
            ax.text(x, start_y - i * line_height, line, fontsize=fontsize,
                    ha='center', va='center', color=text_color,
                    fontweight='bold', fontfamily='sans-serif', zorder=3)
    else:
        ax.text(x, y, text, fontsize=fontsize, ha='center', va='center',
                color=text_color, fontweight='bold', fontfamily='sans-serif', zorder=3)
    return box


def draw_arrow(ax, x1, y1, x2, y2, color=COLORS['gray'], style='->', lw=2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw),
                zorder=1)


def save_fig(fig, name):
    fig.savefig(f'{name}.png', dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    print(f"  -> {name}.png")


# ==============================================================================
# FASE 1: EL PROBLEMA (Motivacion)
# ==============================================================================

def diagram_01_the_problem():
    """Sin orquestacion vs Con orquestacion"""
    fig, ax = setup_figure((16, 9), "01 - El Problema: Por que necesitas orquestacion?")

    # --- Lado izquierdo: Sin orquestacion ---
    ax.text(2.5, 8.5, "Sin Orquestacion", fontsize=16, ha='center',
            fontweight='bold', color=COLORS['error'])

    # Developer icon (circle)
    draw_box(ax, 1, 7, 1.8, 0.6, "Tu (manual)", COLORS['gray'])
    draw_arrow(ax, 1.9, 7, 2.5, 6.5, COLORS['error'])

    scripts = [
        (2.5, 6.2, "script_1.py"),
        (2.5, 5.2, "script_2.py"),
        (2.5, 4.2, "script_3.py"),
    ]
    for x, y, name in scripts:
        draw_box(ax, x, y, 1.8, 0.6, name, COLORS['light_red'],
                text_color=COLORS['error'], border_color=COLORS['error'])

    draw_arrow(ax, 2.5, 5.9, 2.5, 5.5, COLORS['error'], '->')
    draw_arrow(ax, 2.5, 4.9, 2.5, 4.5, COLORS['error'], '->')

    # X mark for failure
    ax.text(3.7, 4.2, "FALLO!", fontsize=12, color=COLORS['error'],
            fontweight='bold', style='italic')
    ax.plot([3.4, 3.6], [4.4, 4.0], color=COLORS['error'], lw=3)
    ax.plot([3.4, 3.6], [4.0, 4.4], color=COLORS['error'], lw=3)

    # Problems list
    problems = [
        "No sabes que fallo",
        "No hay reintentos",
        "No hay logs centralizados",
        "Ejecucion manual",
        "No reproducible",
    ]
    for i, p in enumerate(problems):
        ax.text(2.5, 3.2 - i * 0.5, f"  {p}", fontsize=10, ha='center',
                color=COLORS['error'], fontfamily='sans-serif')

    # --- Separador ---
    ax.plot([5, 5], [1, 9], color=COLORS['light_gray'], lw=2, ls='--')
    ax.text(5, 0.5, "VS", fontsize=18, ha='center', fontweight='bold',
            color=COLORS['gray'])

    # --- Lado derecho: Con orquestacion ---
    ax.text(7.5, 8.5, "Con Orquestacion (Prefect)", fontsize=16, ha='center',
            fontweight='bold', color=COLORS['success'])

    draw_box(ax, 7.5, 7.2, 2.5, 0.7, "@flow: mi_pipeline", COLORS['prefect_blue'])

    tasks_right = [
        (6.2, 6, "@task: cargar"),
        (7.5, 6, "@task: validar"),
        (8.8, 6, "@task: entrenar"),
    ]
    for x, y, name in tasks_right:
        draw_box(ax, x, y, 1.8, 0.55, name, COLORS['success'], fontsize=9)

    draw_arrow(ax, 7.5, 6.85, 6.2, 6.3, COLORS['prefect_blue'])
    draw_arrow(ax, 7.5, 6.85, 7.5, 6.3, COLORS['prefect_blue'])
    draw_arrow(ax, 7.5, 6.85, 8.8, 6.3, COLORS['prefect_blue'])
    draw_arrow(ax, 6.8, 5.75, 7.2, 5.75, COLORS['success'], '->')
    draw_arrow(ax, 7.8, 5.75, 8.5, 5.75, COLORS['success'], '->')

    # Dashboard
    draw_box(ax, 7.5, 4.8, 3.5, 0.7, "Dashboard: estado, logs, metricas",
             COLORS['light_blue'], text_color=COLORS['prefect_dark'],
             border_color=COLORS['prefect_blue'])

    # Benefits
    benefits = [
        "Reintentos automaticos",
        "Logs centralizados",
        "Ejecucion programada (cron)",
        "Reproducible y versionado",
        "Alertas ante fallos",
    ]
    for i, b in enumerate(benefits):
        ax.text(7.5, 3.7 - i * 0.5, f"  {b}", fontsize=10, ha='center',
                color=COLORS['success'], fontfamily='sans-serif')

    save_fig(fig, '01_el_problema')


def diagram_02_five_pillars():
    """Los 5 pilares de la orquestacion"""
    fig, ax = setup_figure((16, 9), "02 - Los 5 Pilares de la Orquestacion")

    pillars = [
        (1.5, "1. Definir\nPasos", "Cada paso es una\nfuncion con @task",
         COLORS['prefect_blue'], COLORS['light_blue']),
        (3.5, "2. Conectar\nen Flujo", "Los pasos forman\nun grafo con @flow",
         COLORS['teal'], COLORS['light_teal']),
        (5.5, "3. Automatizar\nEjecucion", "Cron, intervalos,\ntriggers",
         COLORS['orange'], COLORS['light_orange']),
        (7.5, "4. Observar\ny Reaccionar", "Dashboard, logs,\nartefactos",
         COLORS['purple'], COLORS['light_purple']),
        (9.5, "5. Manejar\nErrores", "Retries, alertas,\nfallbacks",
         COLORS['error'], COLORS['light_red']),
    ]

    # Base line
    ax.plot([1, 10], [3.5, 3.5], color=COLORS['light_gray'], lw=3, zorder=0)

    for x, title, desc, color, bg_color in pillars:
        # Pillar box
        draw_box(ax, x, 6.5, 1.7, 2.0, "", bg_color, border_color=color,
                style='round,pad=0.15')
        ax.text(x, 7.1, title, fontsize=12, ha='center', va='center',
                fontweight='bold', color=color, fontfamily='sans-serif')
        ax.text(x, 5.9, desc, fontsize=9, ha='center', va='center',
                color=COLORS['gray'], fontfamily='sans-serif')

        # Pillar base
        draw_box(ax, x, 4.2, 1.5, 0.7, "", color)

        # Connection
        ax.plot([x, x], [3.5, 5.45], color=color, lw=3, zorder=1)

        # Number circle
        circle = plt.Circle((x, 4.2), 0.3, color='white', zorder=3)
        ax.add_patch(circle)
        ax.text(x, 4.2, str(pillars.index((x, title, desc, color, bg_color)) + 1),
                fontsize=14, ha='center', va='center', fontweight='bold',
                color=color, zorder=4)

    # Bottom label
    ax.text(5.5, 2.5, "Estos principios aplican a CUALQUIER orquestador:\nPrefect, Airflow, Mage, Dagster, Kestra...",
            fontsize=12, ha='center', va='center', color=COLORS['gray'],
            fontfamily='sans-serif', style='italic',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=COLORS['light_gray'],
                     edgecolor='none'))

    save_fig(fig, '02_cinco_pilares')


# ==============================================================================
# FASE 2: CONCEPTOS CORE (Building Blocks)
# ==============================================================================

def diagram_03_flow_and_task():
    """Flow y Task: los building blocks de Prefect"""
    fig, ax = setup_figure((16, 10), "03 - Conceptos Core: @flow y @task")

    # --- Code side (left) ---
    ax.text(2.8, 8.5, "Tu Codigo Python", fontsize=14, ha='center',
            fontweight='bold', color=COLORS['gray'])

    code_lines = [
        ("from prefect import flow, task", COLORS['gray']),
        ("", COLORS['gray']),
        ("@task                    # Paso individual", COLORS['success']),
        ("def cargar_datos():", COLORS['black']),
        ("    return pd.read_csv('data.csv')", COLORS['black']),
        ("", COLORS['gray']),
        ("@task                    # Paso individual", COLORS['success']),
        ("def entrenar(datos):", COLORS['black']),
        ("    model.fit(datos)", COLORS['black']),
        ("", COLORS['gray']),
        ("@flow                    # Pipeline completo", COLORS['prefect_blue']),
        ("def mi_pipeline():", COLORS['black']),
        ("    datos = cargar_datos()", COLORS['black']),
        ("    entrenar(datos)", COLORS['black']),
    ]

    code_bg = FancyBboxPatch((0.3, 2.8), 4.8, 5.5, boxstyle='round,pad=0.2',
                              facecolor='#263238', edgecolor='#37474F', linewidth=2)
    ax.add_patch(code_bg)

    for i, (line, color) in enumerate(code_lines):
        text_color = '#4FC3F7' if '@task' in line or '@flow' in line else '#E0E0E0'
        if '# ' in line:
            parts = line.split('# ')
            ax.text(0.6, 7.9 - i * 0.35, parts[0], fontsize=8.5,
                    fontfamily='monospace', color=text_color, va='center')
            ax.text(0.6 + len(parts[0]) * 0.085, 7.9 - i * 0.35, f'# {parts[1]}',
                    fontsize=8.5, fontfamily='monospace', color='#78909C', va='center')
        else:
            ax.text(0.6, 7.9 - i * 0.35, line, fontsize=8.5,
                    fontfamily='monospace', color=text_color, va='center')

    # --- Arrow from code to concepts ---
    draw_arrow(ax, 5.3, 5.5, 6.0, 5.5, COLORS['prefect_blue'], '->', lw=3)
    ax.text(5.65, 5.8, "Prefect\nentiende", fontsize=9, ha='center',
            color=COLORS['prefect_blue'], fontfamily='sans-serif')

    # --- Concepts side (right) ---
    ax.text(8, 8.5, "Lo Que Prefect Ve", fontsize=14, ha='center',
            fontweight='bold', color=COLORS['prefect_dark'])

    # Flow box (container)
    flow_box = FancyBboxPatch((6.2, 3.0), 3.6, 4.8, boxstyle='round,pad=0.2',
                               facecolor=COLORS['light_blue'],
                               edgecolor=COLORS['prefect_blue'],
                               linewidth=3, linestyle='-')
    ax.add_patch(flow_box)
    ax.text(8, 7.5, "@flow: mi_pipeline", fontsize=13, ha='center',
            fontweight='bold', color=COLORS['prefect_dark'])

    # Task boxes inside
    draw_box(ax, 8, 6.3, 2.5, 0.8, "@task: cargar_datos", COLORS['success'])
    draw_box(ax, 8, 4.6, 2.5, 0.8, "@task: entrenar", COLORS['success'])

    draw_arrow(ax, 8, 5.9, 8, 5.0, COLORS['success'], '->', lw=2.5)
    ax.text(8.4, 5.45, "datos", fontsize=10, color=COLORS['success'],
            fontfamily='sans-serif', style='italic')

    # --- What Prefect adds (bottom) ---
    features = [
        (1.5, 1.8, "Estado", "Pending -> Running\n-> Completed/Failed"),
        (4.0, 1.8, "Logs", "Captura automatica\nde print() y logger"),
        (6.5, 1.8, "Tiempos", "Duracion de cada\ntask y flow"),
        (9.0, 1.8, "Reintentos", "Si falla, reintenta\nautomaticamente"),
    ]

    ax.text(5, 2.7, "Lo que Prefect agrega automaticamente:", fontsize=11,
            ha='center', color=COLORS['prefect_dark'], fontweight='bold')

    for x, y, title, desc in features:
        draw_box(ax, x, y, 2.0, 1.0, "", COLORS['light_blue'],
                border_color=COLORS['prefect_blue'], style='round,pad=0.1')
        ax.text(x, y + 0.2, title, fontsize=10, ha='center',
                fontweight='bold', color=COLORS['prefect_dark'])
        ax.text(x, y - 0.2, desc, fontsize=8, ha='center',
                color=COLORS['gray'])

    save_fig(fig, '03_flow_y_task')


def diagram_04_task_graph():
    """Grafo de dependencias entre tasks"""
    fig, ax = setup_figure((16, 9), "04 - Grafo de Dependencias: Como se conectan los Tasks")

    # Flow container
    flow_bg = FancyBboxPatch((0.5, 1.5), 9, 7, boxstyle='round,pad=0.3',
                              facecolor=COLORS['light_blue'],
                              edgecolor=COLORS['prefect_blue'],
                              linewidth=2, alpha=0.3)
    ax.add_patch(flow_bg)
    ax.text(5, 8.2, "@flow: duration_prediction_pipeline", fontsize=13,
            ha='center', fontweight='bold', color=COLORS['prefect_dark'])

    # Tasks
    tasks = {
        'load': (2.5, 6.5, "cargar_datos\n(data_loader)", COLORS['prefect_blue']),
        'validate': (2.5, 4.5, "validar_datos\n(transformer)", COLORS['teal']),
        'features': (5, 4.5, "crear_features\n(DictVectorizer)", COLORS['teal']),
        'optimize': (7.5, 6.5, "optimizar_params\n(Optuna 20 trials)", COLORS['orange']),
        'train': (7.5, 4.5, "entrenar_modelo\n(XGBoost)", COLORS['purple']),
        'log': (5, 2.5, "registrar_en_mlflow\n(metricas + modelo)", COLORS['success']),
    }

    for key, (x, y, text, color) in tasks.items():
        draw_box(ax, x, y, 2.2, 1.0, "", color, alpha=0.9)
        lines = text.split('\n')
        ax.text(x, y + 0.15, lines[0], fontsize=10, ha='center',
                color='white', fontweight='bold')
        ax.text(x, y - 0.2, lines[1], fontsize=8, ha='center',
                color='#E0E0E0')

    # Arrows showing data flow
    draw_arrow(ax, 2.5, 6.0, 2.5, 5.0, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 3.6, 4.5, 3.9, 4.5, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 6.1, 4.5, 6.4, 4.5, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 7.5, 6.0, 7.5, 5.0, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 5, 4.0, 5, 3.0, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 7.5, 4.0, 5.6, 2.8, COLORS['gray'], '->', lw=2)

    # Data labels on arrows
    ax.text(2.1, 5.5, "df", fontsize=9, color=COLORS['gray'], style='italic')
    ax.text(3.6, 4.7, "df_clean", fontsize=9, color=COLORS['gray'], style='italic')
    ax.text(5.8, 4.7, "X, y", fontsize=9, color=COLORS['gray'], style='italic')
    ax.text(7.1, 5.5, "best_params", fontsize=9, color=COLORS['gray'], style='italic')

    # Legend
    ax.text(5, 1.2, "Cada flecha = datos que pasan de un task al siguiente.\n"
            "Prefect ejecuta los tasks en el orden correcto automaticamente.",
            fontsize=10, ha='center', color=COLORS['gray'], style='italic')

    save_fig(fig, '04_grafo_dependencias')


def diagram_05_states():
    """Estados de ejecucion de un flow/task"""
    fig, ax = setup_figure((16, 8), "05 - Ciclo de Vida: Estados de Ejecucion")

    states = [
        (1.5, 5, "SCHEDULED", COLORS['gray'], "Programado\npara ejecutar"),
        (3.5, 5, "PENDING", COLORS['warning'], "En cola,\nesperando"),
        (5.5, 5, "RUNNING", COLORS['prefect_blue'], "Ejecutandose\nahora"),
        (8.0, 6.5, "COMPLETED", COLORS['success'], "Termino\nexitosamente"),
        (8.0, 3.5, "FAILED", COLORS['error'], "Ocurrio\nun error"),
        (5.5, 2, "RETRYING", COLORS['orange'], "Reintentando\n(si tiene retries)"),
    ]

    for x, y, name, color, desc in states:
        draw_box(ax, x, y, 1.8, 1.0, "", color, alpha=0.9)
        ax.text(x, y + 0.2, name, fontsize=10, ha='center',
                fontweight='bold', color='white')
        ax.text(x, y - 0.2, desc, fontsize=7.5, ha='center', color='#E0E0E0')

    # Happy path arrows
    draw_arrow(ax, 2.4, 5, 2.6, 5, COLORS['gray'], '->', lw=2.5)
    draw_arrow(ax, 4.4, 5, 4.6, 5, COLORS['gray'], '->', lw=2.5)
    draw_arrow(ax, 6.4, 5.3, 7.1, 6.2, COLORS['success'], '->', lw=2.5)

    # Failure path
    draw_arrow(ax, 6.4, 4.7, 7.1, 3.8, COLORS['error'], '->', lw=2.5)

    # Retry path
    draw_arrow(ax, 7.1, 3.2, 6.2, 2.3, COLORS['orange'], '->', lw=2)
    draw_arrow(ax, 4.8, 2.3, 4.7, 4.5, COLORS['orange'], '->', lw=2)

    # Labels
    ax.text(5, 8.5, "Cada @flow y @task pasa por estos estados", fontsize=12,
            ha='center', color=COLORS['gray'], style='italic')
    ax.text(7.5, 5, "Exito", fontsize=10, color=COLORS['success'],
            fontweight='bold', rotation=30)
    ax.text(7.5, 4.1, "Error", fontsize=10, color=COLORS['error'],
            fontweight='bold', rotation=-30)
    ax.text(3.5, 2.2, "retry", fontsize=10, color=COLORS['orange'],
            fontweight='bold', rotation=70)

    # Happy path highlight
    ax.annotate('Camino feliz', xy=(5.5, 6.5), fontsize=11,
                color=COLORS['success'], fontweight='bold', ha='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS['light_green'],
                         edgecolor=COLORS['success']))

    save_fig(fig, '05_estados_ejecucion')


# ==============================================================================
# FASE 3: RESILIENCIA (Hacerlo Robusto)
# ==============================================================================

def diagram_06_retries():
    """Mecanismo de reintentos"""
    fig, ax = setup_figure((16, 9), "06 - Reintentos Automaticos: @task(retries=3)")

    # Code snippet
    code_bg = FancyBboxPatch((0.3, 6.5), 4.0, 2.0, boxstyle='round,pad=0.15',
                              facecolor='#263238', edgecolor='#37474F', linewidth=2)
    ax.add_patch(code_bg)
    code_lines = [
        "@task(retries=3, retry_delay_seconds=10)",
        "def descargar_datos(url):",
        "    response = httpx.get(url)",
        "    return response.json()",
    ]
    for i, line in enumerate(code_lines):
        color = '#4FC3F7' if '@task' in line else '#E0E0E0'
        ax.text(0.5, 8.1 - i * 0.35, line, fontsize=8.5,
                fontfamily='monospace', color=color)

    # Timeline
    ax.plot([1, 9.5], [4.5, 4.5], color=COLORS['light_gray'], lw=2)
    ax.text(5, 5.5, "Linea de Tiempo de Ejecucion", fontsize=13, ha='center',
            fontweight='bold', color=COLORS['prefect_dark'])

    attempts = [
        (2, "Intento 1", COLORS['error'], "FAILED\nTimeout", False),
        (4, "Intento 2", COLORS['error'], "FAILED\nConnection\nrefused", False),
        (6, "Intento 3", COLORS['error'], "FAILED\n500 Error", False),
        (8, "Intento 4", COLORS['success'], "COMPLETED\nDatos OK!", True),
    ]

    for x, label, color, status, success in attempts:
        # Circle on timeline
        circle = plt.Circle((x, 4.5), 0.15, color=color, zorder=3)
        ax.add_patch(circle)

        # Status box
        draw_box(ax, x, 3.2, 1.5, 1.0, "", color if not success else COLORS['success'],
                alpha=0.15, border_color=color)
        ax.text(x, 3.2, status, fontsize=8, ha='center', color=color,
                fontweight='bold')

        ax.text(x, 5.0, label, fontsize=9, ha='center', color=color,
                fontweight='bold')

    # Delay arrows
    for i in range(3):
        x1 = 2 + i * 2 + 0.3
        x2 = 4 + i * 2 - 0.3
        ax.annotate('', xy=(x2, 4.5), xytext=(x1, 4.5),
                    arrowprops=dict(arrowstyle='->', color=COLORS['orange'],
                                   lw=1.5, linestyle='--'))
        ax.text((x1 + x2) / 2, 4.8, "10s", fontsize=8, ha='center',
                color=COLORS['orange'])

    # Bottom explanation
    ax.text(5, 1.5, "Sin retries: tu pipeline falla y te enteras horas despues.\n"
            "Con retries: Prefect reintenta automaticamente.\n"
            "El delay entre reintentos evita saturar el servicio externo.",
            fontsize=11, ha='center', color=COLORS['gray'],
            bbox=dict(boxstyle='round,pad=0.5', facecolor=COLORS['light_gray'],
                     edgecolor='none'))

    save_fig(fig, '06_reintentos')


def diagram_07_caching():
    """Como funciona el caching de tasks"""
    fig, ax = setup_figure((16, 9), "07 - Caching: No repitas trabajo innecesario")

    # --- First run ---
    ax.text(2.5, 8.5, "Primera Ejecucion", fontsize=14, ha='center',
            fontweight='bold', color=COLORS['prefect_blue'])

    run1_tasks = [
        (2.5, 7.2, "cargar_datos", "45 seg", COLORS['prefect_blue']),
        (2.5, 5.8, "crear_features", "30 seg", COLORS['teal']),
        (2.5, 4.4, "entrenar_modelo", "120 seg", COLORS['purple']),
    ]
    for x, y, name, time, color in run1_tasks:
        draw_box(ax, x, y, 2.5, 0.8, f"{name} ({time})", color, fontsize=9)

    draw_arrow(ax, 2.5, 6.8, 2.5, 6.2, COLORS['gray'])
    draw_arrow(ax, 2.5, 5.4, 2.5, 4.8, COLORS['gray'])

    ax.text(2.5, 3.5, "Total: 195 seg", fontsize=12, ha='center',
            fontweight='bold', color=COLORS['prefect_blue'])

    # --- Separator ---
    ax.plot([5, 5], [3, 9], color=COLORS['light_gray'], lw=2, ls='--')

    # --- Second run (with cache) ---
    ax.text(7.5, 8.5, "Segunda Ejecucion (con cache)", fontsize=14, ha='center',
            fontweight='bold', color=COLORS['success'])

    # Cached tasks
    draw_box(ax, 7.5, 7.2, 2.5, 0.8, "cargar_datos (CACHE)", COLORS['light_green'],
             text_color=COLORS['success'], border_color=COLORS['success'], fontsize=9)
    ax.text(9.2, 7.2, "0 seg!", fontsize=10, color=COLORS['success'], fontweight='bold')

    draw_box(ax, 7.5, 5.8, 2.5, 0.8, "crear_features (CACHE)", COLORS['light_green'],
             text_color=COLORS['success'], border_color=COLORS['success'], fontsize=9)
    ax.text(9.2, 5.8, "0 seg!", fontsize=10, color=COLORS['success'], fontweight='bold')

    draw_box(ax, 7.5, 4.4, 2.5, 0.8, "entrenar_modelo (120 seg)", COLORS['purple'],
             fontsize=9)

    draw_arrow(ax, 7.5, 6.8, 7.5, 6.2, COLORS['gray'])
    draw_arrow(ax, 7.5, 5.4, 7.5, 4.8, COLORS['gray'])

    ax.text(7.5, 3.5, "Total: 120 seg (-38%)", fontsize=12, ha='center',
            fontweight='bold', color=COLORS['success'])

    # Code snippet
    code_bg = FancyBboxPatch((1.5, 1.0), 7, 1.5, boxstyle='round,pad=0.15',
                              facecolor='#263238', edgecolor='#37474F', linewidth=2)
    ax.add_patch(code_bg)
    ax.text(5, 2.0, '@task(cache_expiration=timedelta(hours=24))', fontsize=10,
            fontfamily='monospace', color='#4FC3F7', ha='center')
    ax.text(5, 1.5, '# Si los datos no cambian, no los recalcula', fontsize=9,
            fontfamily='monospace', color='#78909C', ha='center')

    save_fig(fig, '07_caching')


# ==============================================================================
# FASE 4: DEPLOYMENT (Hacerlo correr)
# ==============================================================================

def diagram_08_deployment():
    """Deployment y scheduling"""
    fig, ax = setup_figure((16, 9), "08 - Deployment: De script local a ejecucion automatica")

    # Level progression
    levels = [
        (1.2, 7, "Nivel 1\nEjecucion directa",
         "python pipeline.py",
         "Tu lo ejecutas\nmanualmente", COLORS['gray']),
        (3.7, 7, "Nivel 2\n.serve()",
         "flow.serve(name='mi-deploy')",
         "El flow queda\nescuchando peticiones", COLORS['prefect_blue']),
        (6.2, 7, "Nivel 3\n.serve() + cron",
         "flow.serve(cron='0 2 * * *')",
         "Se ejecuta solo\ntodos los dias a las 2am", COLORS['teal']),
        (8.7, 7, "Nivel 4\nprefect.yaml",
         "prefect deploy --all",
         "Config declarativa\nmultiples deployments", COLORS['purple']),
    ]

    for x, y, title, code, desc, color in levels:
        # Card
        draw_box(ax, x, y, 2.1, 2.5, "", COLORS['white'],
                border_color=color, style='round,pad=0.15')
        ax.text(x, 8.0, title, fontsize=10, ha='center',
                fontweight='bold', color=color)

        # Code in card
        code_bg = FancyBboxPatch((x - 0.95, 6.6), 1.9, 0.6, boxstyle='round,pad=0.05',
                                  facecolor='#263238', edgecolor='none')
        ax.add_patch(code_bg)
        ax.text(x, 6.9, code, fontsize=6.5, fontfamily='monospace',
                color='#4FC3F7', ha='center')

        ax.text(x, 6.1, desc, fontsize=8, ha='center', color=COLORS['gray'])

    # Arrow progression
    for i in range(3):
        x = 2.3 + i * 2.5
        draw_arrow(ax, x, 7, x + 0.4, 7, COLORS['gray'], '->', lw=2)

    # Cron explanation
    ax.text(5, 4.0, "Expresiones Cron: Cuando se ejecuta?", fontsize=14,
            ha='center', fontweight='bold', color=COLORS['prefect_dark'])

    cron_box = FancyBboxPatch((1, 1.5), 8, 2.0, boxstyle='round,pad=0.2',
                               facecolor=COLORS['light_blue'],
                               edgecolor=COLORS['prefect_blue'], linewidth=2)
    ax.add_patch(cron_box)

    cron_examples = [
        ("* * * * *", "minuto  hora  dia  mes  dia_semana", ""),
        ("0 2 * * *", "Todos los dias a las 2:00 AM", ""),
        ("*/5 * * * *", "Cada 5 minutos", ""),
        ("0 9 * * 1-5", "Lunes a viernes a las 9 AM", ""),
        ("0 0 1 * *", "El primer dia de cada mes a medianoche", ""),
    ]

    for i, (cron, desc, _) in enumerate(cron_examples):
        y = 3.1 - i * 0.35
        ax.text(2, y, cron, fontsize=9, fontfamily='monospace',
                color=COLORS['prefect_dark'], fontweight='bold')
        ax.text(5.5, y, desc, fontsize=9, color=COLORS['gray'])

    save_fig(fig, '08_deployment')


def diagram_09_architecture():
    """Arquitectura de Prefect"""
    fig, ax = setup_figure((16, 10), "09 - Arquitectura de Prefect: Como funciona por dentro")

    # --- Your Code (left) ---
    ax.text(2, 9, "Tu Codigo", fontsize=13, ha='center',
            fontweight='bold', color=COLORS['gray'])

    draw_box(ax, 2, 7.5, 2.5, 1.2, "", COLORS['light_gray'],
             border_color=COLORS['gray'])
    ax.text(2, 7.8, "@flow + @task", fontsize=11, ha='center',
            fontweight='bold', color=COLORS['gray'])
    ax.text(2, 7.2, "pipeline.py", fontsize=9, ha='center',
            color=COLORS['gray'], style='italic')

    # --- Prefect Server (center) ---
    server_bg = FancyBboxPatch((3.8, 3.5), 4.4, 5.5, boxstyle='round,pad=0.3',
                                facecolor=COLORS['light_blue'],
                                edgecolor=COLORS['prefect_blue'],
                                linewidth=3, alpha=0.5)
    ax.add_patch(server_bg)
    ax.text(6, 8.7, "Prefect Server / Cloud", fontsize=14, ha='center',
            fontweight='bold', color=COLORS['prefect_dark'])

    # API
    draw_box(ax, 6, 7.5, 2.5, 0.8, "API REST", COLORS['prefect_blue'])

    # Scheduler
    draw_box(ax, 5, 6.0, 1.8, 0.7, "Scheduler", COLORS['teal'], fontsize=10)

    # Database
    draw_box(ax, 7, 6.0, 1.8, 0.7, "Database", COLORS['orange'], fontsize=10)
    ax.text(7, 5.4, "(SQLite/Postgres)", fontsize=7, ha='center', color=COLORS['gray'])

    # Orchestration engine
    draw_box(ax, 6, 4.5, 2.5, 0.8, "Motor de\nOrquestacion", COLORS['purple'], fontsize=10)

    # Internal arrows
    draw_arrow(ax, 6, 7.1, 5, 6.35, COLORS['gray'])
    draw_arrow(ax, 6, 7.1, 7, 6.35, COLORS['gray'])
    draw_arrow(ax, 5, 5.65, 6, 4.9, COLORS['gray'])
    draw_arrow(ax, 7, 5.65, 6, 4.9, COLORS['gray'])

    # --- UI (right) ---
    ax.text(9, 9, "Dashboard UI", fontsize=13, ha='center',
            fontweight='bold', color=COLORS['purple'])

    draw_box(ax, 9, 7.5, 2.0, 1.2, "", COLORS['light_purple'],
             border_color=COLORS['purple'])
    ax.text(9, 7.8, "localhost:4200", fontsize=10, ha='center',
            fontweight='bold', color=COLORS['purple'])
    ax.text(9, 7.2, "Flows, Runs,\nLogs, Artifacts", fontsize=8, ha='center',
            color=COLORS['gray'])

    # Arrows between components
    draw_arrow(ax, 3.2, 7.5, 3.8, 7.5, COLORS['prefect_blue'], '->', lw=2.5)
    ax.text(3.5, 7.8, "REST\nAPI", fontsize=8, ha='center', color=COLORS['prefect_blue'])

    draw_arrow(ax, 7.3, 7.5, 7.9, 7.5, COLORS['purple'], '->', lw=2.5)

    # --- Self-hosted vs Cloud ---
    ax.text(3, 2.5, "Self-hosted (gratis)", fontsize=12, ha='center',
            fontweight='bold', color=COLORS['teal'])
    draw_box(ax, 3, 1.5, 3.0, 1.2, "", COLORS['light_teal'],
             border_color=COLORS['teal'])
    ax.text(3, 1.8, "prefect server start", fontsize=9, ha='center',
            fontfamily='monospace', color=COLORS['teal'])
    ax.text(3, 1.2, "Todo en tu maquina\nSQLite local", fontsize=8,
            ha='center', color=COLORS['gray'])

    ax.text(7.5, 2.5, "Prefect Cloud (managed)", fontsize=12, ha='center',
            fontweight='bold', color=COLORS['prefect_blue'])
    draw_box(ax, 7.5, 1.5, 3.0, 1.2, "", COLORS['light_blue'],
             border_color=COLORS['prefect_blue'])
    ax.text(7.5, 1.8, "app.prefect.cloud", fontsize=9, ha='center',
            fontfamily='monospace', color=COLORS['prefect_blue'])
    ax.text(7.5, 1.2, "Hosted por Prefect\nTier gratuito disponible", fontsize=8,
            ha='center', color=COLORS['gray'])

    save_fig(fig, '09_arquitectura')


# ==============================================================================
# FASE 5: ML-SPECIFIC (Aplicacion a ML)
# ==============================================================================

def diagram_10_ml_pipeline():
    """Pipeline completo de ML con Prefect"""
    fig, ax = setup_figure((16, 12), "10 - Pipeline de ML Completo: NYC Taxi con Prefect + MLflow")

    # Main flow label
    ax.text(5, 9.2, "@flow: duration_prediction_pipeline", fontsize=15,
            ha='center', fontweight='bold', color=COLORS['prefect_dark'],
            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS['light_blue'],
                     edgecolor=COLORS['prefect_blue'], linewidth=2))

    # Pipeline steps - 2 rows of 3
    steps_row1 = [
        (1.7, 7.5, "Descargar\nDatos", "NYC TLC\nParquet", COLORS['prefect_blue'],
         "read_dataframe()"),
        (5, 7.5, "Validar\nDatos", "Volumen +\nNulos", COLORS['teal'],
         "validate_data()"),
        (8.3, 7.5, "Crear\nFeatures", "DictVectorizer\nPU/DO Location", COLORS['teal'],
         "create_features()"),
    ]
    steps_row2 = [
        (1.7, 5.3, "Optimizar\nParams", "Optuna\n20 trials", COLORS['orange'],
         "optimize_hyperparams()"),
        (5, 5.3, "Entrenar\nModelo", "XGBoost\nbest_params", COLORS['purple'],
         "train_model()"),
        (8.3, 5.3, "Registrar\nen MLflow", "Metricas +\nModelo", COLORS['success'],
         "mlflow.log_*()"),
    ]

    for steps_row in [steps_row1, steps_row2]:
        for x, y, title, desc, color, func in steps_row:
            draw_box(ax, x, y, 2.6, 1.6, "", color)
            ax.text(x, y + 0.35, title, fontsize=10, ha='center',
                    fontweight='bold', color='white')
            ax.text(x, y - 0.15, desc, fontsize=8, ha='center', color='#E0E0E0')
            ax.text(x, y - 0.55, func, fontsize=7, ha='center',
                    fontfamily='monospace', color='#B0BEC5')

    # Arrows row 1
    draw_arrow(ax, 3.05, 7.5, 3.65, 7.5, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 6.35, 7.5, 6.95, 7.5, COLORS['gray'], '->', lw=2)
    # Arrow from row1 to row2
    draw_arrow(ax, 8.3, 6.65, 8.3, 6.15, COLORS['gray'], '->', lw=2)
    ax.plot([8.3, 1.7], [6.4, 6.4], color=COLORS['gray'], lw=1.5, ls='--', zorder=0)
    draw_arrow(ax, 1.7, 6.4, 1.7, 6.15, COLORS['gray'], '->', lw=2)
    # Arrows row 2
    draw_arrow(ax, 3.05, 5.3, 3.65, 5.3, COLORS['gray'], '->', lw=2)
    draw_arrow(ax, 6.35, 5.3, 6.95, 5.3, COLORS['gray'], '->', lw=2)

    # Data labels
    ax.text(3.35, 7.8, "df_train", fontsize=8, ha='center', color=COLORS['gray'], style='italic')
    ax.text(6.65, 7.8, "df_clean", fontsize=8, ha='center', color=COLORS['gray'], style='italic')
    ax.text(3.35, 5.6, "best_params", fontsize=8, ha='center', color=COLORS['gray'], style='italic')
    ax.text(6.65, 5.6, "run_id", fontsize=8, ha='center', color=COLORS['gray'], style='italic')

    # Integration boxes below
    integrations = [
        (2, 2.5, "NYC TLC Dataset", "Datos publicos de taxis\nen formato Parquet",
         COLORS['prefect_blue']),
        (5, 2.5, "Prefect Dashboard", "Estado, logs,\nartefactos visuales",
         COLORS['purple']),
        (8, 2.5, "MLflow Tracking", "Metricas, modelo,\nModel Registry",
         COLORS['orange']),
    ]

    for x, y, title, desc, color in integrations:
        draw_box(ax, x, y, 2.6, 1.5, "", COLORS['white'],
                border_color=color, style='round,pad=0.15')
        ax.text(x, y + 0.35, title, fontsize=10, ha='center',
                fontweight='bold', color=color)
        ax.text(x, y - 0.2, desc, fontsize=8, ha='center', color=COLORS['gray'])

    # Arrows from pipeline to integrations
    draw_arrow(ax, 1.7, 4.45, 2, 3.3, COLORS['prefect_blue'], '->', lw=1.5)
    draw_arrow(ax, 5, 4.45, 5, 3.3, COLORS['purple'], '->', lw=1.5)
    draw_arrow(ax, 8.3, 4.45, 8, 3.3, COLORS['orange'], '->', lw=1.5)

    # Command to run
    code_bg = FancyBboxPatch((2, 0.5), 6, 0.7, boxstyle='round,pad=0.1',
                              facecolor='#263238', edgecolor='#37474F', linewidth=2)
    ax.add_patch(code_bg)
    ax.text(5, 0.85, "$ uv run python pipeline.py --year 2025 --month 1",
            fontsize=10, fontfamily='monospace', color='#4FC3F7', ha='center')

    save_fig(fig, '10_pipeline_ml_completo')


def diagram_11_prefect_mlflow():
    """Integracion Prefect + MLflow"""
    fig, ax = setup_figure((16, 9), "11 - Integracion Prefect + MLflow: Quien hace que?")

    # Prefect side
    prefect_bg = FancyBboxPatch((0.5, 1.5), 4, 6.5, boxstyle='round,pad=0.3',
                                 facecolor=COLORS['light_blue'],
                                 edgecolor=COLORS['prefect_blue'],
                                 linewidth=3, alpha=0.4)
    ax.add_patch(prefect_bg)
    ax.text(2.5, 7.7, "Prefect", fontsize=16, ha='center',
            fontweight='bold', color=COLORS['prefect_dark'])
    ax.text(2.5, 7.2, "Orquestacion", fontsize=11, ha='center',
            color=COLORS['prefect_blue'], style='italic')

    prefect_items = [
        (2.5, 6.3, "Cuando ejecutar (cron)"),
        (2.5, 5.5, "En que orden (grafo)"),
        (2.5, 4.7, "Que hacer si falla (retries)"),
        (2.5, 3.9, "Estado general (dashboard)"),
        (2.5, 3.1, "Artefactos (resumenes)"),
        (2.5, 2.3, "Logs de ejecucion"),
    ]
    for x, y, text in prefect_items:
        draw_box(ax, x, y, 3.2, 0.55, text, COLORS['prefect_blue'], fontsize=9)

    # MLflow side
    mlflow_bg = FancyBboxPatch((5.5, 1.5), 4, 6.5, boxstyle='round,pad=0.3',
                                facecolor=COLORS['light_orange'],
                                edgecolor=COLORS['orange'],
                                linewidth=3, alpha=0.4)
    ax.add_patch(mlflow_bg)
    ax.text(7.5, 7.7, "MLflow", fontsize=16, ha='center',
            fontweight='bold', color=COLORS['orange'])
    ax.text(7.5, 7.2, "Experiment Tracking", fontsize=11, ha='center',
            color=COLORS['orange'], style='italic')

    mlflow_items = [
        (7.5, 6.3, "Que parametros usaste"),
        (7.5, 5.5, "Que metricas obtuviste"),
        (7.5, 4.7, "Que modelo entrenaste"),
        (7.5, 3.9, "Comparar experimentos"),
        (7.5, 3.1, "Versionado de modelos"),
        (7.5, 2.3, "Model Registry"),
    ]
    for x, y, text in mlflow_items:
        draw_box(ax, x, y, 3.2, 0.55, text, COLORS['orange'], fontsize=9)

    # Center: where they connect
    ax.text(5, 4.7, "+", fontsize=30, ha='center', va='center',
            fontweight='bold', color=COLORS['gray'])

    # Bottom summary
    ax.text(5, 0.8, "Prefect responde: CUANDO y COMO se ejecuta el pipeline\n"
            "MLflow responde: QUE resultados produjo cada ejecucion",
            fontsize=12, ha='center', color=COLORS['gray'],
            bbox=dict(boxstyle='round,pad=0.5', facecolor=COLORS['light_gray'],
                     edgecolor='none'))

    save_fig(fig, '11_prefect_mlflow')


def diagram_12_ecosystem():
    """Panorama de orquestadores"""
    fig, ax = setup_figure((16, 10), "12 - Panorama: Orquestadores de ML/Data")

    # Timeline / complexity axis
    ax.annotate('', xy=(9.5, 1.5), xytext=(0.5, 1.5),
                arrowprops=dict(arrowstyle='->', color=COLORS['gray'], lw=2))
    ax.text(5, 0.8, "Complejidad de setup / Curva de aprendizaje", fontsize=11,
            ha='center', color=COLORS['gray'], style='italic')
    ax.text(0.5, 1.1, "Facil", fontsize=9, color=COLORS['success'])
    ax.text(9.0, 1.1, "Complejo", fontsize=9, color=COLORS['error'])

    # Orchestrators positioned by complexity
    orchestrators = [
        (1.5, 5, "Mage", "UI visual\nTipo notebook\n~8k stars",
         COLORS['mage_purple'], "Prototipos\nEnseñanza"),
        (3.5, 5, "Prefect", "Code-first\nPython nativo\n~18k stars",
         COLORS['prefect_blue'], "ML/DS\nStartups"),
        (5.7, 5, "Dagster", "Assets-first\nTipado fuerte\n~12k stars",
         COLORS['dagster_blue'], "Data Eng\nContratos"),
        (8, 5, "Airflow", "DAGs, standard\nEmpresarial\n~38k stars",
         COLORS['airflow_teal'], "Enterprise\nETL complejo"),
    ]

    for x, y, name, desc, color, usecase in orchestrators:
        # Main card
        draw_box(ax, x, y, 1.8, 3.0, "", COLORS['white'],
                border_color=color, style='round,pad=0.15')
        ax.text(x, y + 1.1, name, fontsize=14, ha='center',
                fontweight='bold', color=color)
        ax.text(x, y + 0.1, desc, fontsize=8, ha='center', color=COLORS['gray'])

        # Use case badge
        draw_box(ax, x, y - 1.0, 1.5, 0.55, usecase, color, fontsize=8)

    # Highlight Prefect
    highlight = FancyBboxPatch((2.45, 3.3), 2.1, 3.4, boxstyle='round,pad=0.15',
                                facecolor='none', edgecolor=COLORS['success'],
                                linewidth=3, linestyle='--')
    ax.add_patch(highlight)
    ax.text(3.5, 7.0, "Usado en\neste curso", fontsize=10, ha='center',
            fontweight='bold', color=COLORS['success'],
            bbox=dict(boxstyle='round,pad=0.2', facecolor=COLORS['light_green'],
                     edgecolor=COLORS['success']))

    # Key insight
    ax.text(5, 8.5, "La herramienta importa menos que entender el concepto.\n"
            "Los 5 pilares de orquestacion aplican a TODAS estas herramientas.",
            fontsize=12, ha='center', color=COLORS['prefect_dark'],
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=COLORS['light_blue'],
                     edgecolor=COLORS['prefect_blue']))

    save_fig(fig, '12_panorama_orquestadores')


# ==============================================================================
# Main
# ==============================================================================

if __name__ == '__main__':
    print("Generando diagramas educativos de Orquestacion...")
    print("=" * 50)

    print("\nFASE 1: El Problema (Motivacion)")
    diagram_01_the_problem()
    diagram_02_five_pillars()

    print("\nFASE 2: Conceptos Core (Building Blocks)")
    diagram_03_flow_and_task()
    diagram_04_task_graph()
    diagram_05_states()

    print("\nFASE 3: Resiliencia (Hacerlo Robusto)")
    diagram_06_retries()
    diagram_07_caching()

    print("\nFASE 4: Deployment (Hacerlo Correr)")
    diagram_08_deployment()
    diagram_09_architecture()

    print("\nFASE 5: ML-Specific (Aplicacion a ML)")
    diagram_10_ml_pipeline()
    diagram_11_prefect_mlflow()
    diagram_12_ecosystem()

    print("\n" + "=" * 50)
    print("12 diagramas generados exitosamente!")
    print("\nSecuencia pedagogica:")
    print("  01-02: POR QUE orquestacion (motivacion)")
    print("  03-05: QUE es Prefect (conceptos core)")
    print("  06-07: COMO hacerlo robusto (resiliencia)")
    print("  08-09: COMO desplegarlo (deployment)")
    print("  10-12: COMO aplicarlo a ML (integracion)")
