from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.connectors import (
    GoogleCalendarPushIn,
    GoogleCalendarSyncIn,
    HubSpotSyncIn,
    WhatsAppCloudSendIn,
)
from app.schemas.voice import VoiceCallCreateIn
from app.services.capture_service import issue_scoped_credential
from app.services.connectors_service import (
    push_appointment_to_google_calendar,
    send_whatsapp_cloud_message,
    sync_google_calendar_events,
    sync_hubspot_crm,
)
from app.services.consent_authorization_service import record_suppression
from app.services.post_v1_service import confirm_appointment
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.voice_service import start_voice_call
from app.tenant_models.operations import Cliente, Message
from app.tenant_models.opportunity import Opportunity, PipelineStage
from app.tenant_models.phase5_integrations import ConnectorSyncCursor, ExternalEntityMapping
from app.tenant_models.phase6_extensions import VoiceCallSegment, VoiceCallSession
from app.tenant_models.post_v1 import CalendarAppointment
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 22, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)


class ConnectorsAndMediaStreamTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int) -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="pro",
            status="active",
        )
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.add(
                TenantRuntime(
                    auth_tenant_id=auth_id,
                    tenant_slug=schema,
                    schema_name=schema,
                    tenant_code=schema,
                    ingest_key_hash="unused",
                    plan="pro",
                    status="active",
                )
            )
            db.commit()
        return tenant

    def _override_db(self):
        def _db_gen():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = _db_gen
        self.addCleanup(app.dependency_overrides.clear)

    def test_whatsapp_cloud_outbound_window_suppression_and_idempotency(self):
        tenant = self._seed_tenant("tenant_p8_wac", 9701)
        with Session(self.engine) as db:
            record_suppression(
                db,
                tenant,
                channel="whatsapp",
                destination="+56990001",
                purpose="marketing",
                reason="baja",
                source="unsubscribe_link",
                recorded_at=T0,
            )

            calls: list[dict] = []

            def fake_transport(method: str, url: str, headers: dict, body: dict | None):
                calls.append({"method": method, "url": url, "body": body})
                return 200, {}, {"messages": [{"id": "wamid.cloud.77"}]}

            with self.assertRaises(HTTPException) as sup_err:
                send_whatsapp_cloud_message(
                    db,
                    tenant,
                    WhatsAppCloudSendIn(
                        phone_number_id="pn-1",
                        to_phone="+56990001",
                        template_name="promo_v1",
                        outside_24h_window=True,
                        idempotency_key="wac-sup-1",
                    ),
                    actor_user_id="mgr-1",
                    transport=fake_transport,
                    now=T0,
                )
            self.assertEqual(sup_err.exception.status_code, 403)

            with self.assertRaises(HTTPException) as win_err:
                send_whatsapp_cloud_message(
                    db,
                    tenant,
                    WhatsAppCloudSendIn(
                        phone_number_id="pn-1",
                        to_phone="+56990002",
                        body_text="Hola libre",
                        outside_24h_window=True,
                        idempotency_key="wac-win-1",
                    ),
                    actor_user_id="mgr-1",
                    transport=fake_transport,
                    now=T0,
                )
            self.assertEqual(win_err.exception.status_code, 422)

            res1 = send_whatsapp_cloud_message(
                db,
                tenant,
                WhatsAppCloudSendIn(
                    phone_number_id="pn-1",
                    to_phone="+56990002",
                    template_name="recordatorio_cita",
                    outside_24h_window=True,
                    idempotency_key="wac-ok-1",
                ),
                actor_user_id="mgr-1",
                transport=fake_transport,
                now=T0,
            )
            self.assertFalse(res1["duplicate"])
            self.assertEqual(res1["provider_message_id"], "wamid.cloud.77")

            res2 = send_whatsapp_cloud_message(
                db,
                tenant,
                WhatsAppCloudSendIn(
                    phone_number_id="pn-1",
                    to_phone="+56990002",
                    template_name="recordatorio_cita",
                    outside_24h_window=True,
                    idempotency_key="wac-ok-1",
                ),
                actor_user_id="mgr-1",
                transport=fake_transport,
                now=T0,
            )
            self.assertTrue(res2["duplicate"])
            self.assertEqual(len(calls), 1)
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 1)

    def test_google_calendar_bidirectional_sync_and_410_cursor_reset(self):
        tenant = self._seed_tenant("tenant_p8_gcal", 9702)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            c = Cliente(rut="gc-1", nombre="Ana Agenda")
            db.add(c)
            db.commit()
            db.refresh(c)

            appt = confirm_appointment(
                db,
                tenant,
                resource_key="sala-1",
                client_id=c.id,
                title="Demo KronFlow",
                starts_at=T0,
                ends_at=T1,
                idempotency_key="appt-gc-1",
                actor_user_id="mgr-1",
                now=T0,
            )

            seen_requests: list[tuple[str, str]] = []

            def gcal_transport(method: str, url: str, headers: dict, body: dict | None):
                seen_requests.append((method, url))
                if method == "POST":
                    return 200, {}, {"id": "gcal_ev_100", "etag": "etag_1"}
                if "syncToken=tok_expired" in url:
                    return 410, {}, {"error": "Sync token is no longer valid"}
                return 200, {}, {
                    "items": [{"id": "gcal_ev_100", "status": "cancelled"}],
                    "nextSyncToken": "tok_new_2",
                }

            pushed = push_appointment_to_google_calendar(
                db,
                tenant,
                appt["id"],
                GoogleCalendarPushIn(calendar_id="primary", access_token="oauth_tok"),
                actor_user_id="mgr-1",
                transport=gcal_transport,
                now=T0,
            )
            self.assertEqual(pushed["remote_event_id"], "gcal_ev_100")

            # Seed expired cursor to test 410 full rebuild + remote cancellation reflection.
            bind_tenant_session(db, tenant.schema_name)
            db.add(
                ConnectorSyncCursor(
                    connection_ref="google_calendar:primary",
                    stream_name="events",
                    cursor_value="tok_expired",
                    status="ok",
                    synced_count=0,
                    updated_at=T0,
                )
            )
            db.commit()

            synced = sync_google_calendar_events(
                db,
                tenant,
                GoogleCalendarSyncIn(calendar_id="primary", access_token="oauth_tok"),
                actor_user_id="mgr-1",
                transport=gcal_transport,
                now=T1,
            )
            self.assertTrue(synced["cursor_reset"])
            self.assertEqual(synced["cursor_value"], "tok_new_2")

            bind_tenant_session(db, tenant.schema_name)
            appt_after = db.get(CalendarAppointment, appt["id"])
            self.assertEqual(appt_after.status, "cancelled")

    def test_hubspot_sync_rate_limit_429_pause_and_conflict(self):
        tenant = self._seed_tenant("tenant_p8_hs", 9703)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            c = Cliente(rut="hs-1", nombre="Carlos Hub", email="carlos@hub.test")
            db.add(c)
            db.flush()
            stage = PipelineStage(slug="nuevo", name="Nuevo", position=1)
            db.add(stage)
            db.flush()
            db.add(Opportunity(contact_id=c.id, stage_id=stage.id, title="Deal Hub", currency="USD", owner_user_id="u1"))
            db.commit()

            def hs_429_transport(method: str, url: str, headers: dict, body: dict | None):
                return 429, {"Retry-After": "30"}, {"message": "Rate limit exceeded"}

            paused = sync_hubspot_crm(
                db,
                tenant,
                HubSpotSyncIn(stream="contacts", batch_size=25, access_token="hs_pat"),
                actor_user_id="mgr-1",
                transport=hs_429_transport,
                now=T0,
            )
            self.assertEqual(paused["status"], "paused")
            self.assertTrue(paused["rate_limited"])
            self.assertEqual(paused["retry_after_seconds"], 30)

            def hs_ok_transport(method: str, url: str, headers: dict, body: dict | None):
                return 200, {}, {
                    "cursor": "hs_cur_1",
                    "results": [{"id": "hs-contact-55", "local_id": str(c.id), "version": "1"}],
                }

            ok_res = sync_hubspot_crm(
                db,
                tenant,
                HubSpotSyncIn(stream="contacts", batch_size=25, access_token="hs_pat"),
                actor_user_id="mgr-1",
                transport=hs_ok_transport,
                now=T1,
            )
            self.assertEqual(ok_res["synced"], 1)
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(ExternalEntityMapping)), 1)
            cur = db.scalar(select(ConnectorSyncCursor).where(ConnectorSyncCursor.connection_ref == "hubspot"))
            self.assertEqual(cur.status, "ok")

    def test_twilio_media_stream_websocket_barge_in_and_stop(self):
        tenant = self._seed_tenant("tenant_p8_ws", 9704)
        self._override_db()

        with Session(self.engine) as db:
            cred = issue_scoped_credential(db, tenant, name="voice-ws", scopes=["mcp:invoke"], created_by="mgr-1")
            call = start_voice_call(
                db,
                tenant,
                VoiceCallCreateIn(
                    provider="twilio",
                    external_call_id="CA_WS_1",
                    direction="inbound",
                    from_number="+56912340000",
                    to_number="+56220009999",
                ),
                now=T0,
            )

        client = TestClient(app)
        with client.websocket_connect(f"/api/v1/voice/media-stream/{call['id']}?api_key={cred['api_key']}") as ws:
            ws.send_json({"event": "start", "streamSid": "MZ_1"})
            conn_msg = ws.receive_json()
            self.assertEqual(conn_msg["event"], "connected")
            self.assertEqual(conn_msg["streamSid"], "MZ_1")

            ws.send_json({"event": "media", "media": {"payload": "QUFBQQ=="}})
            ws.send_json({"event": "barge_in", "transcript": "Espera, prefiero hablar con ventas"})
            clear_msg = ws.receive_json()
            self.assertEqual(clear_msg["event"], "clear")
            self.assertEqual(clear_msg["streamSid"], "MZ_1")

            ws.send_json({"event": "stop", "billable_seconds": 18})
            stop_msg = ws.receive_json()
            self.assertEqual(stop_msg["event"], "stopped")
            self.assertEqual(stop_msg["frames_received"], 1)

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            after_call = db.get(VoiceCallSession, call["id"])
            self.assertEqual(after_call.status, "completed")
            self.assertEqual(after_call.billable_seconds, 18)
            self.assertEqual(after_call.barge_in_count, 1)
            seg = db.scalar(select(VoiceCallSegment).where(VoiceCallSegment.call_id == call["id"]))
            self.assertEqual(seg.transcript, "Espera, prefiero hablar con ventas")
