import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(__file__).resolve().parent.parent
private_path = root / os.environ.get("JWT_PRIVATE_KEY_PATH", "keys/jwt_private.pem")
public_path = root / os.environ.get("JWT_PUBLIC_KEY_PATH", "keys/jwt_public.pem")
if private_path.resolve() == public_path.resolve():
    raise SystemExit("JWT private and public keys must use different paths.")

if private_path.is_file():
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
else:
    if public_path.exists():
        raise SystemExit("Restore the private JWT key that corresponds to the existing public key.")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as private_file:
        private_file.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

public_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

public_path.parent.mkdir(parents=True, exist_ok=True)
public_path.write_bytes(public_bytes)
print("Claves JWT preparadas.")
