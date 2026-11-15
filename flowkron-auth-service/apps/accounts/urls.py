from django.urls import path

from apps.security.views import ClientCredentialsView, EmailConfirmView, EmailResendView, ForgotPasswordView, InitialPasswordView, JwksView, MfaConfirmView, MfaSetupView, MfaVerifyView, ResetPasswordView, TokenIntrospectionView

from .views import ChangePasswordView, LoginView, LogoutAllView, LogoutView, MeView, ProfileAvatarView, ProfileView, TaggedTokenRefreshView, TaggedTokenVerifyView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TaggedTokenRefreshView.as_view(), name="auth-refresh"),
    path("verify/", TaggedTokenVerifyView.as_view(), name="auth-token-verify"),
    path("client-credentials/", ClientCredentialsView.as_view(), name="client-credentials"),
    path("introspect/", TokenIntrospectionView.as_view(), name="token-introspect"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("logout-all/", LogoutAllView.as_view(), name="auth-logout-all"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("profile/avatar/", ProfileAvatarView.as_view(), name="auth-profile-avatar"),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),
    path("password/initial-set/", InitialPasswordView.as_view(), name="password-initial-set"),
    path("password/forgot/", ForgotPasswordView.as_view(), name="password-forgot"),
    path("password/reset/", ResetPasswordView.as_view(), name="password-reset"),
    path("email/resend/", EmailResendView.as_view(), name="email-resend"),
    path("email/confirm/", EmailConfirmView.as_view(), name="email-confirm"),
    path("mfa/setup/", MfaSetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MfaConfirmView.as_view(), name="mfa-confirm"),
    path("mfa/verify/", MfaVerifyView.as_view(), name="mfa-verify"),
    path("jwks/", JwksView.as_view(), name="jwks"),
]
