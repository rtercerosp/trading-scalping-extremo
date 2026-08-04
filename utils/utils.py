# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from datetime import datetime

# Crear un método estático para poder convertir una divisa a otra
class Utils():

    def __init__(self):
        """
        Initializes the object.
        """
        pass

    @staticmethod
    def dateprint() -> str:
        """
        Returns the current date and time in the format "dd/mm/yyyy HH:MM:SS.sss".
        Uses the system local timezone.
        """
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
