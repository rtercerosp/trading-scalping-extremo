# performance_analyzer.py

import os
import logging
from dotenv import load_dotenv, find_dotenv

# Importaciones de los módulos del framework
from platform_connector.platform_connector import PlatformConnector
from brain.trading_brain import TradingBrain
from utils.utils import Utils

# --- CONFIGURACIÓN BÁSICA ---
# Configura un logging mínimo para evitar errores de los módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def analyze_performance():
    """
    Inicializa los componentes necesarios en modo 'solo lectura',
    carga el historial de trading a través del TradingBrain y
    muestra un reporte de rendimiento completo.
    """
    print("==================================================")
    print("||      ANALIZADOR DE RENDIMIENTO DEL BOT       ||")
    print("==================================================")

    # --- Carga de Configuración ---
    # Es necesario para que el PlatformConnector pueda inicializarse si fuera necesario,
    # aunque el TradingBrain carga principalmente del archivo JSON.
    env_file_path: str | None = find_dotenv()
    if env_file_path:
        logging.info(f"Cargando configuración desde: {env_file_path}")
        load_dotenv(env_file_path)
    else:
        logging.warning("No se encontró archivo .env. Se usarán valores por defecto.")

    # --- Inicialización Mínima de Módulos ---
    # Solo necesitamos los componentes de los que depende el TradingBrain para su inicialización.
    # No se usarán para trading en vivo, solo para cargar datos.
    try:
        # El conector es necesario para algunas funciones internas del cerebro y otros módulos.
        connector = PlatformConnector(symbol_list=[]) # Lista de símbolos vacía, no haremos peticiones de mercado.
        
        # El cerebro necesita referencias a otros módulos, aunque no los use activamente para este análisis.
        # Pasamos `None` a las dependencias que no son estrictamente necesarias para el reporte.
        brain = TradingBrain(
            events_queue=None, 
            data_provider=None, 
            portfolio=None, 
            order_executor=None, 
            connector=connector
        )
    except Exception as e:
        print()
        print(f"[X] Error al inicializar los módulos del framework: {e}")
        print("Asegúrate de que la plataforma MetaTrader 5 no necesita estar abierta si la configuración lo requiere.")
        return

    # --- Generación y Visualización del Reporte ---
    # El TradingBrain carga el historial automáticamente en su constructor.
    # Ahora solo tenemos que pedirle que genere el reporte.
    if not brain.trade_history:
        print()
        print("No se encontró historial de operaciones en 'trade_history.json'.")
        print("Realiza algunas operaciones con el bot para generar un historial.")
        return
        
    performance_report = brain.get_performance_report()

    print()
    print("--- INICIO DEL REPORTE ---")
    print(performance_report)
    print("--- FIN DEL REPORTE ---")

    print()
    print("[i] Interpretación del Reporte:")
    print("- **Win Rate:** Porcentaje de operaciones ganadoras. Un valor > 50% es generalmente bueno.")
    print("- **Total Profit:** Suma neta de ganancias y pérdidas. Te dice si la estrategia es rentable en general.")
    print("- **Avg Profit:** El beneficio (o pérdida) promedio por operación.")
    print("- El desglose por activo te muestra dónde la estrategia es más fuerte o más débil.")


if __name__ == "__main__":
    # Verificar que el historial existe antes de correr el análisis
    if not os.path.exists("trade_history.json"):
        print("[X] Error: El archivo 'trade_history.json' no existe.")
        print("Ejecuta el bot de trading primero para que se genere un historial de operaciones.")
    else:
        analyze_performance()
