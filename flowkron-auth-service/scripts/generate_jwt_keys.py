from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(__file__).resolve().parent.parent
keys_dir = root / "keys"
keys_dir.mkdir(exist_ok=True)

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
public_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

(keys_dir / "jwt_private.pem").write_bytes(private_bytes)
(keys_dir / "jwt_public.pem").write_bytes(public_bytes)
print(f"Claves JWT creadas en {keys_dir}")
