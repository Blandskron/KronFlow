from rest_framework_simplejwt.tokens import RefreshToken

from apps.rbac.services import permissions_for_membership, roles_for_membership
from apps.sessions.models import UserSession
from apps.sessions.services import evaluate_session_risk
from apps.tenants.entitlements import subscription_summary


class FlowkronRefreshToken(RefreshToken):
    @classmethod
    def for_user_session(cls, user, membership, session, amr="pwd"):
        token = cls.for_user(user)
        token["tenant_id"] = str(membership.tenant_id) if membership else None
        token["membership_id"] = str(membership.id) if membership else None
        token["session_id"] = str(session.id)
        token["roles"] = roles_for_membership(membership)
        token["permissions"] = permissions_for_membership(membership)
        token["subscription"] = subscription_summary(membership.tenant) if membership else None
        token["onboarding_required"] = membership is None
        token["amr"] = amr
        return token


def issue_tokens(user, membership, request, amr="pwd"):
    session = UserSession.objects.create_from_request(user=user, membership=membership, request=request)
    evaluate_session_risk(session, request=request)
    refresh = FlowkronRefreshToken.for_user_session(user, membership, session, amr=amr)
    return refresh, session
