import argparse
import asyncio
import sys
import uuid

from app.config import ConfigurationError, get_settings
from app.email import EmailMessage
from app.resend_provider import ProviderError, ResendEmailProvider


async def run(recipient: str, sender_key: str) -> int:
    settings = get_settings()
    sender = settings.senders.get(sender_key)
    if sender is None:
        print("Error: sender_key desconocido.", file=sys.stderr)
        return 2
    provider = ResendEmailProvider(settings)
    key = f"cli-{uuid.uuid4().hex}"
    try:
        result = await provider.send(EmailMessage(
            sender=sender.from_address,
            recipients=[recipient],
            subject="Prueba Blandskron Email Gateway",
            html="<p>Correo de prueba enviado mediante Resend.</p>",
            text="Correo de prueba enviado mediante Resend.",
            reply_to=sender.reply_to,
            idempotency_key=key,
        ))
    except (ConfigurationError, ProviderError) as exc:
        status = f" http_status={exc.provider_status}" if isinstance(exc, ProviderError) and exc.provider_status else ""
        print(f"Error: {exc}{status}", file=sys.stderr)
        return 1
    print(f"Éxito: message_id={result.message_id}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Envía un correo de prueba mediante el mismo proveedor del gateway.")
    parser.add_argument("--sender-key", required=True)
    parser.add_argument("--to", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.to, args.sender_key)))


if __name__ == "__main__":
    main()
