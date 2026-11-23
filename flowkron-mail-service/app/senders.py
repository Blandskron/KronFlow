from .config import ConfigurationError, SenderConfig, Settings


def resolve_sender(settings: Settings, sender_key: str) -> SenderConfig:
    sender = settings.senders.get(sender_key)
    if sender is None:
        raise ConfigurationError("sender_key desconocido.")
    if "\r" in sender.from_address or "\n" in sender.from_address:
        raise ConfigurationError("Remitente configurado inválido.")
    if sender.reply_to and ("\r" in sender.reply_to or "\n" in sender.reply_to):
        raise ConfigurationError("Reply-to configurado inválido.")
    return sender
