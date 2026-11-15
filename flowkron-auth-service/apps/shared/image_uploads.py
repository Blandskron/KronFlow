from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 3 * 1024 * 1024


def save_uploaded_image(uploaded_file, *, folder: str, max_size: tuple[int, int]) -> str:
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("La imagen no puede superar 3 MB.", code="IMAGE_TOO_LARGE")

    content_type = getattr(uploaded_file, "content_type", "")
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise serializers.ValidationError("Formato no soportado. Usa JPG, PNG o WebP.", code="IMAGE_INVALID_TYPE")

    try:
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
    except (SyntaxError, UnidentifiedImageError, OSError):
        raise serializers.ValidationError("El archivo no es una imagen valida.", code="IMAGE_INVALID")

    try:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(output, format="WEBP", quality=86, method=6)
    except (SyntaxError, UnidentifiedImageError, OSError, ValueError):
        raise serializers.ValidationError("El archivo no es una imagen valida.", code="IMAGE_INVALID")
    output.seek(0)

    safe_folder = str(PurePosixPath(folder))
    path = f"{safe_folder}/{uuid4().hex}.webp"
    return default_storage.save(path, ContentFile(output.read()))


def absolute_media_url(request, stored_path: str) -> str:
    return request.build_absolute_uri(default_storage.url(stored_path))
