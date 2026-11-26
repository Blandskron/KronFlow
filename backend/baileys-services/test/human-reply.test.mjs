import assert from "node:assert/strict";
import { EventEmitter, once } from "node:events";
import { createServer } from "node:http";
import test from "node:test";
import { WhatsAppConnection } from "../dist/connection.js";
import { createHttpServer } from "../dist/http.js";

async function listen(t, server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => server.close());
  return `http://127.0.0.1:${server.address().port}`;
}

test("internal human reply endpoint enforces auth, validation, connection state, withdrawal, and send", async (t) => {
  const token = "t".repeat(40);
  const ev = new EventEmitter();
  const sent = [];
  let releaseWithdraw;
  const withdrawGate = new Promise(resolve => { releaseWithdraw = resolve; });

  const conn = new WhatsAppConnection(
    "unused",
    async () => { await withdrawGate; },
    async () => ({
      socket: {
        ev,
        user: { id: "12025550111:1@s.whatsapp.net" },
        sendMessage: async (jid, payload, opts) => {
          sent.push({ jid, text: payload.text, messageId: opts?.messageId });
          return { key: { id: opts?.messageId ?? "wa-human-1" } };
        },
      },
      saveCreds: async () => {},
    }),
  );

  const sessions = new Map([["7", conn]]);
  const base = await listen(
    t,
    createHttpServer(
      { start: async () => {}, snapshot: () => ({ status: "disconnected" }) },
      token,
      (id) => sessions.get(id) ?? { start: async () => {}, stop: async () => {}, snapshot: () => ({ status: "disconnected" }) },
    ),
  );
  const url = `${base}/internal/baileys/tenants/7/messages`;
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };

  // 1. Unauthorized without bearer.
  const unauth = await fetch(url, { method: "POST", body: JSON.stringify({ phone: "56911112222", text: "Hola" }) });
  assert.equal(unauth.status, 401);

  // 2. Disconnected session -> 409 retryable, definitely not sent.
  const disconn = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ phone: "+56 9 1111 2222", text: "Hola" }),
  });
  assert.equal(disconn.status, 409);
  assert.deepEqual(await disconn.json(), { error: "session_not_connected", sent: false, retryable: true });

  // Connect socket.
  await conn.start();
  ev.emit("connection.update", { connection: "open" });

  // 3. Invalid payload -> 422.
  const bad = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ phone: "abc", text: "   " }),
  });
  assert.equal(bad.status, 422);

  // 4. Connected -> 200 sent with provider_message_id.
  const ok = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ phone: "+56 9 1111 2222", text: "Te atiende un ejecutivo." }),
  });
  assert.equal(ok.status, 200);
  const okBody = await ok.json();
  assert.equal(okBody.status, "sent");
  assert.ok(okBody.provider_message_id);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].jid, "56911112222@s.whatsapp.net");
  assert.equal(sent[0].text, "Te atiende un ejecutivo.");

  // 5. Pending BAJA withdrawal -> 409 consent_withdrawn, not retryable.
  ev.emit("messages.upsert", {
    type: "notify",
    messages: [{
      key: { id: "w-1", remoteJid: "56933334444@s.whatsapp.net" },
      message: { conversation: "BAJA" },
      messageTimestamp: 1760000000,
    }],
  });
  await new Promise(setImmediate);
  const blocked = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ phone: "56933334444", text: "Intento bloqueado" }),
  });
  assert.equal(blocked.status, 409);
  assert.deepEqual(await blocked.json(), { error: "consent_withdrawn", sent: false, retryable: false });
  releaseWithdraw();
  await new Promise(setImmediate);
});
