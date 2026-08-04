# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from ..interfaces.notification_channel_interface import INotificationChannel
from ..properties.properties import TelegramNotificationProperties
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

class TelegramNotificationChannel(INotificationChannel):
    
    def __init__(self, properties: TelegramNotificationProperties) -> None:
        """
        Initializes a new instance of the TelegramNotificationChannel class.

        Args:
            properties (TelegramNotificationProperties): The properties for the Telegram notification channel.

        """
        self._chat_id = properties.chat_id
        self._token = properties.token
    
    async def _async_send_message(self, title: str, message: str):
        """
        Asynchronously sends a formatted message to the Telegram chat.

        Args:
            title (str): The title of the message.
            message (str): The content of the message.
        """
        # Revisa si las credenciales están configuradas para evitar errores
        if not self._token or not self._chat_id or "INTRODUCE" in self._token or self._token.strip().lower() in {"tu tpooken", "tu token", "tu pin", "tu_token_de_bot_de_telegram", "none", ""}:
            return # Falla silenciosamente si no está configurado

        bot = Bot(token=self._token)
        
        # Formatea el mensaje con MarkdownV2, escapando caracteres especiales
        def escape_markdown(text: str) -> str:
            escape_chars = r'_*[]()~`>#+-=|{}.!'
            return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

        safe_title = escape_markdown(title)
        safe_message = escape_markdown(message)
        
        formatted_message = f"*{safe_title}*\n\n{safe_message}"
        
        try:
            await bot.send_message(
                chat_id=self._chat_id, 
                text=formatted_message, 
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except TelegramError as e:
            print(f"ERROR NOTIFICATIONS: Error al enviar notificación de Telegram: {e}")
        except Exception as e:
            print(f"ERROR NOTIFICATIONS: Error inesperado al enviar notificación de Telegram: {e}")
    
    def send_message(self, title: str, message: str):
        """
        Sends a message to the Telegram channel.

        Args:
            title (str): The title of the message.
            message (str): The content of the message.
        """
        # asyncio.run() es simple y suficiente para la estructura de este proyecto.
        asyncio.run(self._async_send_message(title, message))
