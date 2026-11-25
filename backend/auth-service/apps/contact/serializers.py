import re

from rest_framework import serializers

from .models import ContactMessage

HTML_TAG_RE = re.compile(r"<[^>]*>")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SQL_CONTROL_RE = re.compile(r"(--|/\*|\*/|;|\bunion\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\balter\b)", re.IGNORECASE)
PHONE_RE = re.compile(r"^[0-9+()\-\s]{0,32}$")


class ContactMessageSerializer(serializers.ModelSerializer):
    accept_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "company", "phone", "message", "accept_terms", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "name": {"max_length": 120, "trim_whitespace": True},
            "company": {"max_length": 120, "required": False, "allow_blank": True, "trim_whitespace": True},
            "phone": {"max_length": 32, "required": False, "allow_blank": True, "trim_whitespace": True},
            "message": {"max_length": 2000, "trim_whitespace": True},
        }

    def validate_accept_terms(self, value):
        if value is not True:
            raise serializers.ValidationError("Debes aceptar los terminos y la politica de privacidad.")
        return value

    def validate_phone(self, value):
        if value and not PHONE_RE.fullmatch(value):
            raise serializers.ValidationError("El telefono solo puede contener numeros, espacios y simbolos telefonicos.")
        return value

    def validate(self, attrs):
        for field in ["name", "company", "phone", "message"]:
            value = attrs.get(field, "")
            if not value:
                continue
            if CONTROL_CHARS_RE.search(value):
                raise serializers.ValidationError({field: "El campo contiene caracteres no permitidos."})
            if HTML_TAG_RE.search(value):
                raise serializers.ValidationError({field: "No se permite HTML en el formulario."})
            if SQL_CONTROL_RE.search(value):
                raise serializers.ValidationError({field: "El campo contiene una secuencia no permitida."})
        return attrs
