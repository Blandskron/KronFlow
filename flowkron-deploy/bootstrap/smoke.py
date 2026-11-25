"""Exercise a disposable Compose demo project."""

import argparse
import json
import os
import re
import secrets
import subprocess
from http.cookiejar import CookieJar
from urllib.parse import unquote_plus, urlencode
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


def endpoint(variable, default):
    return f"http://localhost:{os.getenv(variable, default)}"


def main(project, standard=False):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    auth = endpoint("AUTH_PORT", "8000")
    operational = endpoint("OPERATIONAL_PORT", "8001")
    agent = endpoint("AGENT_CORE_PORT", "8002")
    landing = endpoint("LANDING_PORT", "8080")
    crm = endpoint("APP_PORT", "8081")

    def fetch(url, payload=None, headers=None, *, form=False):
        body = None
        if payload is not None:
            body = (urlencode(payload) if form else json.dumps(payload)).encode()
        content_type = "application/x-www-form-urlencoded" if form else "application/json"
        req = Request(
            url,
            data=body,
            headers={"Content-Type": content_type, **(headers or {})},
        )
        with opener.open(req, timeout=20) as response:
            if response.headers.get_content_type() != "application/json":
                return response.read().decode()
            data = json.load(response)
            return data.get("data", data)

    def expect_rejected(code, url, payload=None, headers=None):
        try:
            fetch(url, payload, headers)
        except HTTPError as error:
            assert error.code == code, (url, error.code)
        else:
            raise AssertionError(f"Expected HTTP {code} for {url}")

    assert "KronFlow" in fetch(landing)
    assert "KronFlow" in fetch(crm + "/login")
    assert fetch(operational + "/readyz")["status"] == "ready"
    assert fetch(agent + "/ready")["status"] == "ready"

    if standard:
        compose = ["docker", "compose", "-p", project]
        check = "from django.contrib.auth import get_user_model; assert not get_user_model().objects.filter(is_superuser=True).exists()"
        subprocess.run(compose + ["exec", "-T", "flowkron-auth-service", "python", "manage.py", "shell", "-c", check], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        email = f"smoke-{secrets.token_hex(5)}@example.com"
        password = f"Synthetic-{secrets.token_urlsafe(24)}"
        assert fetch(auth + "/api/v1/auth/signup/", {"email": email})["accepted"]
        # Console mail in this disposable instance only. Never print tokens or logs.
        mail = subprocess.check_output(compose + ["logs", "--no-color", "--tail", "80", "flowkron-auth-service"], text=True, encoding="utf-8", errors="replace")
        match = re.search(r"/registrarse#token=([^\s]+)", mail)
        assert match, "No test verification mail was emitted"
        assert fetch(auth + "/api/v1/auth/signup/complete/", {"token": unquote_plus(match.group(1)), "password": password})["created"]
        session = fetch(auth + "/api/v1/auth/login/", {"email": email, "password": password})
        assert session["onboarding_required"]
        onboarded = fetch(auth + "/api/v1/tenants/onboarding/", {"name": "Synthetic Open Workspace"}, {"Authorization": f"Bearer {session['access']}"})
        headers = {"Authorization": f"Bearer {onboarded['access']}", "X-Tenant-ID": str(onboarded["tenant_id"])}
        assert "TENANT_OWNER" in onboarded["roles"]
        assert isinstance(fetch(operational + "/api/v1/leads", headers=headers), dict)
        print("Verified clean standard stack, no superuser, account verification, first workspace and access to its Operational data.")
        return

    compose = ["docker", "compose", "-f", "compose.demo.yaml", "-p", project, "exec", "-T"]
    password = subprocess.check_output(
        compose
        + [
            "flowkron-auth-service",
            "cat",
            "/run/flowkron/bootstrap_admin_password",
        ],
        text=True,
    ).strip()
    session = fetch(
        auth + "/api/v1/auth/login/",
        {"email": "admin@example.com", "password": password},
    )
    assert session["tenant_id"] and not session["subscription"]["requires_paid_plan"]
    headers = {
        "Authorization": f"Bearer {session['access']}",
        "X-Tenant-ID": str(session["tenant_id"]),
    }
    me = fetch(auth + "/api/v1/auth/me/", headers=headers)
    assert me["tenant"]["name"] == "BLANDSKRON"
    assert "TENANT_OWNER" in me["roles"] and "crm.manage" in me["permissions"]
    assert me["user"]["profile"]["email_verified_at"]

    django_login = auth + "/admin/login/"
    admin_login_form = fetch(django_login)
    csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', admin_login_form)
    assert csrf_match, "Django admin did not return a login form."
    fetch(
        django_login,
        {
            "username": "admin@example.com",
            "password": password,
            "csrfmiddlewaretoken": csrf_match.group(1),
            "next": "/admin/auth/user/",
        },
        {"Referer": django_login},
        form=True,
    )
    django_users = fetch(auth + "/admin/auth/user/")
    assert 'id="changelist"' in django_users and "admin@example.com" in django_users
    assert isinstance(fetch(operational + "/api/v1/leads", headers=headers), dict)
    whatsapp = fetch(f"{auth}/api/v1/tenants/{session['tenant_id']}/whatsapp/", headers=headers)
    assert whatsapp["status"] == "disconnected"
    documents = fetch(agent + "/api/v1/context/documents", headers=headers)
    assert "agente-demo-blandskron.txt" in json.dumps(documents)
    refresh_headers = {**headers, "Authorization": f"Bearer {session['refresh']}"}
    expect_rejected(401, operational + "/api/v1/leads", headers=refresh_headers)
    expect_rejected(401, agent + "/api/v1/context/documents", headers=refresh_headers)
    fetch(
        agent + "/api/v1/context/documents/upload",
        {
            "title": "Compose smoke test",
            "filename": "compose-smoke.md",
            "content": "La palabra de prueba del despliegue es orquidea.",
            "status": "active",
        },
        headers,
    )
    simulation = fetch(
        agent + "/api/v1/agent/simulate",
        {
            "channel": "webchat",
            "conversation_id": "compose-smoke",
            "customer": {"external_id": "synthetic"},
            "message": {"content": "¿Cuál es la palabra de prueba del despliegue?"},
        },
        headers,
    )
    assert simulation["sources"] and "orquidea" in simulation["reply"]["content"].lower()

    csrf = fetch(auth + "/api/v1/contact/csrf/", headers={"Origin": landing})
    contact = fetch(
        auth + "/api/v1/contact/messages/",
        {
            "name": "Persona de prueba",
            "email": "compose-test@example.com",
            "message": "Este mensaje comprueba el formulario de contacto.",
            "accept_terms": True,
        },
        {"Origin": landing, "X-CSRFToken": csrf["csrfToken"]},
    )
    assert contact["id"]
    tenant = f"{auth}/api/v1/tenants/{session['tenant_id']}"
    assert fetch(tenant + "/suspend/", {}, headers)["status"] == "suspended"
    expect_rejected(403, operational + "/api/v1/leads", headers=headers)
    expect_rejected(403, agent + "/api/v1/context/documents", headers=headers)
    assert fetch(tenant + "/activate/", {}, headers)["status"] == "active"
    assert isinstance(fetch(operational + "/api/v1/leads", headers=headers), dict)
    print("Verified landing, sign in, admin, tenant data, agent simulation, contact, refresh rejection and workspace suspension/reactivation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--standard", action="store_true", help="Exercise a clean, disposable standard Compose project.")
    args = parser.parse_args()
    main(args.project, args.standard)
