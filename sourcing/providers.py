from .canboso import CanbosoClient
from .models import SupplierBot
from .sson import SsonDigitalClient


def client_for_bot(bot: SupplierBot):
    if bot.bot_source == SupplierBot.BotSource.SSON:
        return SsonDigitalClient(api_key=bot.api_key, base_url=bot.base_url)
    return CanbosoClient(api_key=bot.api_key, base_url=bot.base_url)
