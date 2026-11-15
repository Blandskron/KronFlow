import assert from "node:assert/strict";
import { EventEmitter, once } from "node:events";
import { createServer } from "node:http";
import test from "node:test";
import { WhatsAppConnection } from "../dist/connection.js";
import { createHttpServer } from "../dist/http.js";
import { normalizeInbound, operationalIngest, tenantIngest } from "../dist/ingest.js";

function inbound(key = {}) {
  return {
    key: { id: "example-id", remoteJid: "12025550138@s.whatsapp.net", ...key },
    message: { conversation: "Mensaje de prueba" },
    messageTimestamp: 1760000000
  };
}

async function listen(t, server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => server.close());
  return `http://127.0.0.1:${server.address().port}`;
}

test("normalizes incoming text and only derives a LID phone from an alternate phone JID", () => {
  const message = normalizeInbound(inbound());
  assert.equal(message.external_message_id, "baileys:12025550138:example-id");
  assert.equal(message.phone, "12025550138");
  assert.equal(message.sent_at, "2025-10-09T08:53:20.000Z");
  assert.equal(normalizeInbound(inbound({ remoteJid: "123@lid" })), undefined);
  assert.equal(normalizeInbound(inbound({
    remoteJid: "123@lid",
    remoteJidAlt: "12025550138@s.whatsapp.net"
  })).external_thread_id, message.external_thread_id);
  assert.equal(normalizeInbound(inbound({ remoteJid: "123@g.us" })), undefined);
  assert.equal(normalizeInbound(inbound({ fromMe: true })), undefined);
  assert.equal(normalizeInbound({ ...inbound(), messageTimestamp: 0 }), undefined);
});

test("consults tenant-scoped consent before sending normalized data to Operational", async (t) => {
  const calls = [];
  let consent = false;
  const provider = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    calls.push({ url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ consentimiento_datos: consent }));
  });
  const base = await listen(t, provider);
  const ingest = operationalIngest({
    OPERATIONAL_SERVICE_URL: base,
    BAILEYS_INGEST_TENANT_CODE: "tenant-lab",
    BAILEYS_INGEST_KEY: "synthetic"
  });
  const message = normalizeInbound(inbound());
  await ingest(message);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/v1/ingest/whatsapp/consent?phone=12025550138");
  consent = true;
  await ingest(message);
  assert.equal(calls.length, 3);
  assert.equal(calls[2].url, "/api/v1/ingest/whatsapp/message");
  assert.equal(calls[2].headers["x-tenant-code"], "tenant-lab");
  assert.equal(calls[2].headers["x-ingest-key"], "synthetic");
  assert.deepEqual(JSON.parse(calls[2].body), message);
});

test("shares one socket and clears QR on connection or logout", async () => {
  const ev = new EventEmitter();
  const forwarded = [];
  let opened = 0;
  const connection = new WhatsAppConnection("unused", async (message) => {
    forwarded.push(message);
  }, async () => {
    opened++;
    return { socket: { ev }, saveCreds: async () => {} };
  });
  await Promise.all([connection.start(), connection.start()]);
  assert.equal(opened, 1);
  ev.emit("connection.update", { qr: "synthetic-qr" });
  assert.deepEqual(connection.snapshot(), { status: "qr_pending", qr: "synthetic-qr" });
  ev.emit("connection.update", { connection: "open" });
  assert.deepEqual(connection.snapshot(), { status: "connected", qr: undefined });
  ev.emit("messages.upsert", { type: "append", messages: [inbound()] });
  ev.emit("messages.upsert", { type: "notify", messages: [inbound()] });
  await new Promise(setImmediate);
  assert.equal(forwarded.length, 1);
  ev.emit("connection.update", {
    connection: "close",
    lastDisconnect: { error: { output: { statusCode: 401 } } }
  });
  await connection.start();
  assert.equal(connection.snapshot().status, "pairing_required");
  assert.equal(opened, 1);
});

test("protects QR and connection actions behind the internal bearer", async (t) => {
  const token = "t".repeat(40);
  let starts = 0;
  const base = await listen(t, createHttpServer({
    start: async () => { starts++; },
    snapshot: () => ({ status: "qr_pending", qr: "synthetic-qr" })
  }, token));
  const url = base + "/internal/baileys/session";
  const headers = { Authorization: `Bearer ${token}` };
  assert.equal((await fetch(base + "/health")).status, 200);
  assert.equal((await fetch(url)).status, 401);
  assert.equal((await fetch(url + "/start", { method: "POST" })).status, 401);
  assert.equal(starts, 0);
  const started = await fetch(url + "/start", { method: "POST", headers });
  assert.equal(started.status, 202);
  assert.deepEqual(await started.json(), { status: "qr_pending" });
  const state = await fetch(url, { headers });
  assert.equal(state.headers.get("cache-control"), "no-store");
  assert.match((await state.json()).qr, /^data:image\/png;base64,/);
});

test("isolates tenant QR and disconnect actions behind the internal bearer", async (t) => {
  const token = "t".repeat(40);
  const snapshots = new Map();
  function resolve(id) {
    return {
      start: async () => snapshots.set(id, { status: "qr_pending", qr: "test-" + id }),
      stop: async () => snapshots.delete(id),
      snapshot: () => snapshots.get(id) ?? { status: "disconnected" }
    };
  }
  const base = await listen(t, createHttpServer(resolve("legacy"), token, resolve));
  const headers = { Authorization: `Bearer ${token}` };
  const a = base + "/internal/baileys/tenants/1/session";
  const b = base + "/internal/baileys/tenants/2/session";
  assert.equal((await fetch(a)).status, 401);
  assert.equal((await fetch(a, { method: "POST", headers })).status, 200);
  assert.match((await (await fetch(a, { headers })).json()).qr, /^data:image\/png;base64,/);
  assert.deepEqual(await (await fetch(b, { headers })).json(), { status: "disconnected" });
  await fetch(a, { method: "DELETE", headers });
  assert.deepEqual(await (await fetch(a, { headers })).json(), { status: "disconnected" });
});

test("requires consent, stores each conversation and relays its agent response once", async (t) => {
  const requests = [];
  const replies = [];
  let consent = false;
  let duplicate = false;
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks)) : null;
    requests.push({ url: req.url, headers: req.headers, body });
    let data;
    if (req.url.includes("/consent")) {
      if (body) consent = body.accepted;
      data = { consentimiento_datos: consent };
    } else if (req.url.endsWith("/internal/whatsapp/15")) {
      data = { reply: { content: "Respuesta de prueba" }, requires_human: true };
    } else {
      data = { duplicate };
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data }));
  });
  const url = await listen(t, backend);
  const handler = tenantIngest("15", "synthetic", url, url);
  const message = normalizeInbound(inbound());
  const reply = async (content) => replies.push(content);
  await handler(message, reply);
  await handler(message, reply);
  assert.equal(replies.length, 1);
  assert.ok(requests.every((request) => request.url.includes("/consent")));
  await handler({ ...message, body: "ACEPTO" }, reply);
  await handler(message, reply);
  const agentRequest = requests.find((request) => request.url.endsWith("/internal/whatsapp/15"));
  assert.equal(agentRequest.headers["x-flowkron-tenant"], "15");
  assert.equal(agentRequest.body.message.content, message.body);
  assert.equal(replies.at(-1), "Respuesta de prueba");
  assert.equal(requests.at(-1).body.direction, "outbound");
  assert.ok(requests.some((request) => request.url.endsWith("/handoff")));
  duplicate = true;
  await handler(message, reply);
  assert.equal(replies.length, 3);
});
