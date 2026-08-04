# QUANTDEMY - https://quantdemy.com
# Script para descubrir y listar todos los símbolos disponibles en el bróker.

import MetaTrader5 as mt5
import os
from dotenv import load_dotenv, find_dotenv, set_key


# --- Constants ---
SEPARATOR_LENGTH = 60
SHORT_SEPARATOR_LENGTH = 50
TRUE_STRINGS = ('true', '1', 't', 'y', 'yes')

def discover_and_print_symbols():
    """
    Se conecta a MetaTrader 5, recupera todos los símbolos disponibles del bróker
    y muestra sus nombres en la consola.
    """
    # --- Carga de Configuración ---
    env_file_path: str | None = find_dotenv()
    if env_file_path:
        print(f"ℹ️  Cargando configuración desde: {env_file_path}")
        load_dotenv(env_file_path)
    else:
        print("⚠️ ADVERTENCIA: No se encontró ningún archivo .env. Se usarán variables de entorno del sistema si existen.")
        # Attempt to load from system environment if .env not found
        load_dotenv()

    # --- Verificación de variables de entorno ---
    required_vars: list[str] = ["MT5_PATH", "MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_TIMEOUT"]
    for var in required_vars:
        if not os.getenv(var):
            print(f"🚨 ERROR: La variable de entorno '{var}' no está definida en tu archivo .env.")
            return

    # --- Conexión a MetaTrader 5 ---
    # Usa las mismas credenciales que el bot principal
    path = os.getenv("MT5_PATH")
    try:
        login = int(os.getenv("MT5_LOGIN"))
        timeout = int(os.getenv("MT5_TIMEOUT"))
    except (ValueError, TypeError):
        print("🚨 ERROR: MT5_LOGIN y MT5_TIMEOUT deben ser números enteros en tu archivo .env.")
        return
        
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    portable_str = os.getenv("MT5_PORTABLE", "False").lower()
    portable_bool = portable_str in ('true', '1', 't', 'y', 'yes')

    # --- DIAGNÓSTICO: Imprimir las credenciales que se van a utilizar ---
    login_to_use = login
    server_to_use = server
    path_to_use = path
    print("-" * 60)
    print("ℹ️  INTENTANDO CONECTAR CON LOS SIGUIENTES DATOS:")
    print(f"    - Path:   {path_to_use}") # El path es seguro de mostrar.
    print(f"    - Login:  ********")
    print(f"    - Server: ********")
    print("-" * 60)

    if not mt5.initialize(
        path=path_to_use,
        login=login_to_use,
        password=password,
        server=server_to_use,
        timeout=timeout,
        portable=portable_bool
    ):
        print(f"Fallo al inicializar MT5, error code = {mt5.last_error()}")
        mt5.shutdown()
        return

    account_info: mt5.AccountInfo | None = mt5.account_info()
    if account_info is None:
        print(f"No se pudo obtener la información de la cuenta, error code = {mt5.last_error()}")
        mt5.shutdown()
        return

    # --- CAPA DE SEGURIDAD ADICIONAL ---
    # Warn if a real account is detected, similar to the main connector.
    if account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL:
        print("\n" + "!" * SEPARATOR_LENGTH)
        print("!! ALERTA: Se han detectado credenciales de una cuenta REAL.")
        print("!! Este script está a punto de conectarse a una cuenta con capital en riesgo.")
        print("!" * SEPARATOR_LENGTH + "\n")
        if input("¿Estás SEGURO de que quieres continuar? (y/n): ").lower() != "y":
            mt5.shutdown()
            print("\nOperación cancelada por el usuario. Revisa tu archivo .env")
            return
    # --- FIN DE LA CAPA DE SEGURIDAD ---

    print(f"Conectado a la cuenta #{account_info.login} en {account_info.server}")
    print("-" * 50)
    print("Buscando todos los símbolos disponibles en el bróker...") #
    print("-" * SHORT_SEPARATOR_LENGTH)

    try:
        all_symbols: tuple[mt5.SymbolInfo, ...] | None = mt5.symbols_get()
        if all_symbols:
            all_symbol_names: list[str] = sorted([symbol.name for symbol in all_symbols])
            print(f"Se encontraron {len(all_symbol_names)} símbolos. A continuación se muestra la lista:")
            print("-" * SHORT_SEPARATOR_LENGTH)
            for i, name in enumerate(all_symbol_names):
                print(f"{i+1:4d}: {name}")
            print("-" * SHORT_SEPARATOR_LENGTH)
            
            # --- MENSAJE EXPLICATIVO AÑADIDO ---
            print("\nEste script guardará tu selección en el archivo '.env' bajo la variable 'TRADING_SYMBOLS'.")
            print("Esta es la forma moderna y segura de configurar tu bot, como se indica en el CHANGELOG v1.1.")
            print("💡 Consejo: Asegúrate de que el archivo .env no esté abierto en otro programa antes de continuar.")
            # --- FIN DEL MENSAJE ---
            while True:
                selection: str
                try:
                    selection = input("\nIntroduce los NÚMEROS de los activos que quieres operar, separados por comas (ej: 1, 25, 110): ")
                    selected_indices = [int(i.strip()) - 1 for i in selection.split(',')]
                    
                    selected_symbols = []
                    valid_selection = True
                    for index in selected_indices:
                        if 0 <= index < len(all_symbol_names):
                            selected_symbols.append(all_symbol_names[index])
                        else:
                            print(f"Error: El número {index + 1} está fuera de rango. Inténtalo de nuevo.")
                            valid_selection = False
                            break
                    
                    if valid_selection:
                        symbols_str: str = ",".join(selected_symbols)
                        # Reuse the env_file_path found earlier, or default to .env
                        env_file_to_write: str = env_file_path if env_file_path else ".env"
                        try:
                            set_key(env_file_to_write, "TRADING_SYMBOLS", symbols_str)
                            print("\n✅ ¡Configuración guardada con éxito!")
                            print(f"   Los siguientes símbolos se han guardado en tu archivo .env: {symbols_str}")
                        except PermissionError:
                            print("\n❌ ERROR DE PERMISO: No se pudo escribir en el archivo .env.")
                            print("   Asegúrate de que el archivo no esté abierto en otro programa (como el bot de trading) o que no sea de solo lectura.")
                            print("   Abre tu archivo .env y añade o modifica la siguiente línea al final:")
                            print("-" * 60)
                            print(f'TRADING_SYMBOLS="{symbols_str}"')
                            print("-" * 60)
                        break

                except ValueError:
                    print("Error: Entrada no válida. Asegúrate de introducir solo números separados por comas.")

    finally:
        mt5.shutdown()
        print("\nConexión con MT5 cerrada.")

if __name__ == "__main__":
    discover_and_print_symbols()