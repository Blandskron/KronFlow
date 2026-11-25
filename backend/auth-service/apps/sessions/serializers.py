from rest_framework import serializers

from .models import UserSession


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = ["id", "tenant", "ip_address", "user_agent", "status", "risk_score", "risk_flags", "expires_at", "revoked_at", "token_family", "last_refresh_at", "created_at"]
        read_only_fields = fields
