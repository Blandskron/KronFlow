"""PRV-007 / QG-2: Fast JWT revocation via shared Redis in agent-core."""

from app.core.config import Settings
from app.core.security import REVOCATION_KEY_PREFIX, is_jwt_revoked


class _FakeRedis:
    def __init__(self, store: dict[str, str] | None = None, *, fail: bool = False):
        self.store = dict(store or {})
        self.fail = fail

    def mget(self, keys: list[str]) -> list[str | None]:
        if self.fail:
            raise ConnectionError("synthetic redis outage")
        return [self.store.get(k) for k in keys]


def test_agent_core_jwt_revocation_checks_jti_session_user_tenant_and_fallback():
    settings = Settings(_env_file=None, redis_url="")
    claims = {"jti": "ag-jti-1", "session_id": "88", "user_id": "12", "tenant_id": "5", "iat": 2000}

    assert not is_jwt_revoked(claims, settings, redis_client=_FakeRedis({}))
    assert is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}jti:ag-jti-1": "1"}))
    assert is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}session:88": "1"}))
    assert is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}user:12": "2000"}))
    assert not is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}user:12": "1999"}))
    assert is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}tenant:5": "2010"}))
    assert not is_jwt_revoked(claims, settings, redis_client=_FakeRedis(fail=True))
