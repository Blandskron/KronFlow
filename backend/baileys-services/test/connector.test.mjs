import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { EventEmitter, once } from "node:events";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:http";
import test from "node:test";
import { WAMessageStatus } from "baileys";
import { WhatsAppConnection } from "../dist/connection.js";
import { createHttpServer } from "../dist/http.js";
import { normalizeInbound, operationalIngest, tenantIngest } from "../dist/ingest.js";
import { InboundQueue } from "../dist/inbound-queue.js";
import { normalizeReceipt, ReceiptBuffer } from "../dist/receipts.js";

test("bounds queued work, reserves withdrawals and keeps other senders running", async () => {
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const handled = [];
  const queue = new InboundQueue(() => assert.fail("unexpected job error"), 24);
  queue.enqueue("slow", "message", () => blocked);
  for (let i = 0; i < 1000; i++) queue.enqueue("flood", "message", async () => { handled.push("flood"); });
  assert.equal(queue.size, 4);
  assert.equal(queue.enqueue("other", "message", async () => { handled.push("other"); }), true);
  assert.equal(queue.enqueue("flood", "withdraw", async () => { handled.push("withdrawal"); }), true);
  assert.equal(queue.size, 1);
  assert.deepEqual(handled, ["withdrawal"]);
  release();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(handled, ["withdrawal", "other"]);
  assert.equal(queue.size, 0);
});

test("queue capacity is bounded across distinct senders and clearing cancels pending work", async () => {
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const queue = new InboundQueue(() => {}, 24);
  queue.enqueue("slow", "message", () => blocked);
  for (let i = 0; i < 1000; i++) queue.enqueue(String(i), "message", async () => {});
  assert.equal(queue.size, 8);
  queue.enqueue("active-withdrawal", "withdraw", () => blocked);
  assert.equal(queue.enqueue("pending-withdrawal", "withdraw", async () => {}), true);
  queue.discardNonWithdrawals();
  assert.equal(queue.size, 1);
  release();
  await new Promise(setImmediate);
  assert.equal(queue.size, 0);
});

test("repeated withdrawals leave a slot for another sender's consent", async () => {
  const queue = new InboundQueue(() => assert.fail("unexpected job error"), 24);
  const handled = [];
  const withdraw = async () => {
    handled.push("withdrawal");
    if (handled.length < 10) queue.enqueue("same-sender", "withdraw", withdraw);
  };
  queue.enqueue("same-sender", "withdraw", withdraw);
  queue.enqueue("other", "accept", async () => { handled.push("acceptance"); });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(handled.indexOf("acceptance"), 4);
});

test("ACEPTO preserves sender order and BAJA invalidates an active turn permanently", async () => {
  const queue = new InboundQueue(() => assert.fail("unexpected job error"));
  let finish;
  const blocked = new Promise(resolve => { finish = resolve; });
  const handled = [];
  let current;
  queue.enqueue("contact", "message", async (isCurrent) => {
    current = isCurrent;
    await blocked;
  });
  queue.enqueue("contact", "accept", async () => { handled.push("superseded"); });
  queue.enqueue("contact", "withdraw", async () => { handled.push("withdraw"); });
  queue.enqueue("contact", "accept", async () => { handled.push("accept"); });
  queue.enqueue("other", "accept", async () => { handled.push("other"); });
  await new Promise(setImmediate);
  assert.deepEqual(handled, ["withdraw", "other"]);
  assert.equal(current(), false);
  finish();
  await new Promise(setImmediate);
  assert.deepEqual(handled, ["withdraw", "other", "accept"]);
  assert.equal(current(), false);
});

test("a delayed withdrawal preserves a newer explicit acceptance queued for the same contact", async () => {
  const queue = new InboundQueue(() => assert.fail("unexpected job error"));
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const handled = [];
  queue.enqueue("other", "accept", () => blocked, 10);
  queue.enqueue("contact", "accept", async () => { handled.push("newer acceptance"); }, 30);
  queue.enqueue("contact", "withdraw", async () => { handled.push("older withdrawal"); }, 20);
  release();
  await new Promise(setImmediate);
  assert.deepEqual(handled, ["older withdrawal", "newer acceptance"]);
});

test("stop invalidates a delayed positive workspace check", async () => {
  const directory = await mkdtemp(join(tmpdir(), "flowkron-queue-test-"));
  let allow;
  const authorized = new Promise(resolve => { allow = resolve; });
  let connections = 0;
  const connection = new WhatsAppConnection(directory, undefined, async () => { connections++; }, () => authorized);
  const starting = connection.start();
  const stopping = connection.stop();
  allow(true);
  await Promise.all([starting, stopping]);
  assert.equal(connections, 0);
  assert.equal(connection.snapshot().status, "disconnected");
});

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
  assert.equal(message.provider_message_id, "example-id");
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
  assert.equal(connection.snapshot().qr, "synthetic-qr");
  assert.equal(connection.snapshot().diagnostics.next_action, "scan");
  ev.emit("connection.update", { connection: "open" });
  assert.equal(connection.snapshot().status, "connected");
  assert.equal(connection.snapshot().qr, undefined);
  assert.ok(Date.parse(connection.snapshot().diagnostics.last_connected_at));
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
  assert.equal(connection.snapshot().diagnostics.disconnect_cause, "signed_out");
  assert.equal(connection.snapshot().diagnostics.next_action, "relink");
  assert.deepEqual(connection.snapshot().diagnostics.recent_transitions.map(event => event.status),
    ["pairing_required", "connected", "qr_pending", "connecting"]);
  assert.equal(opened, 1);
});

test("transient disconnect exposes the next retry and an actionable exhaustion state", async (t) => {
  t.mock.timers.enable({ apis: ["Date", "setTimeout"], now: Date.parse("2026-11-19T22:10:00Z") });
  const sockets = [];
  const connection = new WhatsAppConnection("unused", undefined, async () => {
    const ev = new EventEmitter();
    sockets.push(ev);
    return { socket: { ev }, saveCreds: async () => {} };
  });
  await connection.start();
  const close = () => sockets.at(-1).emit("connection.update", { connection: "close" });
  close();
  for (let attempt = 0; attempt < 5; attempt++) {
    const waiting = connection.snapshot().diagnostics;
    const delay = 1000 * 2 ** attempt;
    assert.equal(waiting.next_action, "wait");
    assert.equal(waiting.disconnect_cause, "temporary");
    assert.equal(Date.parse(waiting.next_retry_at) - Date.now(), delay);
    assert.equal(waiting.retry_attempts, attempt);
    t.mock.timers.tick(delay);
    await new Promise(setImmediate);
    assert.equal(sockets.length, attempt + 2);
    close();
  }
  const exhausted = connection.snapshot().diagnostics;
  assert.equal(exhausted.next_retry_at, undefined);
  assert.equal(exhausted.retry_exhausted, true);
  assert.equal(exhausted.next_action, "retry");
  await connection.start();
  assert.equal(connection.snapshot().diagnostics.retry_attempts, 0);
  assert.equal(connection.snapshot().status, "connecting");
});

test("an expired QR cannot be refreshed by a duplicate event or observed in a new process", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-11-19T22:10:00Z") });
  const ev = new EventEmitter();
  const connection = new WhatsAppConnection("unused", undefined, async () => ({
    socket: { ev }, saveCreds: async () => {}
  }));
  await connection.start();
  ev.emit("connection.update", { qr: "first-qr" });
  const initial = connection.snapshot();
  assert.equal(initial.qr, "first-qr");
  t.mock.timers.tick(Date.parse(initial.diagnostics.qr_expires_at) - Date.now());
  ev.emit("connection.update", { qr: "first-qr" });
  assert.equal(connection.snapshot().qr, undefined);
  assert.equal(connection.snapshot().diagnostics.next_action, "wait");
  ev.emit("connection.update", { qr: "new-qr" });
  assert.equal(connection.snapshot().qr, "new-qr");
  const restored = new WhatsAppConnection("unused");
  assert.equal(restored.snapshot().qr, undefined);
  assert.equal(restored.snapshot().diagnostics.qr_issued_at, undefined);
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

test("the tenant API discards a rendered QR if connection status changed", async (t) => {
  const token = "t".repeat(40);
  let reads = 0;
  const session = {
    snapshot: () => ++reads === 1
      ? { status: "qr_pending", qr: "stale-qr", diagnostics: { qr_issued_at: "2026-11-19T22:10:00Z" } }
      : { status: "connected", diagnostics: { next_action: "none" } }
  };
  const base = await listen(t, createHttpServer(session, token, () => session));
  const response = await fetch(base + "/internal/baileys/tenants/1/session", {
    headers: { Authorization: `Bearer ${token}` }
  });
  assert.deepEqual(await response.json(), { status: "connected", diagnostics: { next_action: "none" } });
});

test("requires consent, stores each conversation and relays its agent response once", async (t) => {
  const requests = [];
  const replies = [];
  let consent = false;
  let turnState = "generating";
  let preparedReply;
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
    } else if (req.url.endsWith("/turns/claim")) {
      data = { turn_id: 1, state: turnState, claimed: turnState === "generating", claim_token: "synthetic-claim-token",
        phone: "12025550138", external_thread_id: "12025550138", input_body: body.body };
    } else if (req.url.endsWith("/prepare")) {
      turnState = "prepared";
      preparedReply = body.reply_body;
      data = { state: turnState, reply_body: preparedReply };
    } else if (req.url.endsWith("/begin-send")) {
      turnState = "sending";
      data = { state: turnState, claimed: true };
    } else if (req.url.endsWith("/complete")) {
      turnState = "completed";
      data = { state: turnState };
    } else {
      throw new Error(`Unexpected request: ${req.url}`);
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data }));
  });
  const url = await listen(t, backend);
  const handler = tenantIngest("15", "synthetic", url, url);
  const message = normalizeInbound(inbound());
  const reply = async (content) => {
    replies.push(content);
    return { provider_message_id: "outgoing-provider-id" };
  };
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
  assert.ok(requests.at(-1).url.endsWith("/complete"));
  assert.equal(requests.at(-1).body.provider_message_id, "outgoing-provider-id");
  assert.ok(requests.some((request) => request.url.endsWith("/prepare") && request.body.requires_human));
  await handler(message, reply);
  assert.equal(replies.length, 3);
});

test("an incoming BAJA persists before generation finishes and blocks the ordinary reply", { timeout: 5000 }, async (t) => {
  const requests = [];
  const ev = new EventEmitter();
  const sent = new EventEmitter();
  const started = new EventEmitter();
  const backend = createServer(async (req, res) => {
    const operation = req.url.split("?")[0].split("/").at(-1);
    requests.push([req.method, operation]);
    for await (const _ of req) { /* Drain the synthetic request. */ }
    const answer = (data) => {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ data }));
    };
    if (operation === "consent") {
      answer({ consentimiento_datos: req.method === "GET" });
      if (req.method === "POST") started.emit("withdrawal");
    }
    else if (operation === "claim") answer({
      turn_id: 1, state: "generating", claimed: true, claim_token: "synthetic-claim-token",
      phone: "12025550138", external_thread_id: "12025550138", input_body: "Consulta"
    });
    else if (operation === "15") started.emit("generation", () => answer({
      reply: { content: "Contenido ordinario" }, requires_human: true
    }));
    else if (operation === "release") answer({ state: "received" });
    else res.writeHead(500).end();
  });
  const url = await listen(t, backend);
  const connection = new WhatsAppConnection("unused", tenantIngest("15", "synthetic", url, url), async () => ({
    socket: {
      ev,
      sendMessage: async (jid, { text }) => {
        sent.emit("message", text);
        return { key: { id: "synthetic-ack" } };
      }
    },
    saveCreds: async () => {}
  }));
  await connection.start();
  ev.emit("connection.update", { connection: "open" });
  const generating = once(started, "generation");
  ev.emit("messages.upsert", { type: "notify", messages: [inbound()] });
  const [finishGeneration] = await generating;
  const withdrawal = inbound({ id: "withdrawal" });
  withdrawal.message.conversation = " BAJA ";
  const reply = once(sent, "message");
  const persisted = once(started, "withdrawal");
  ev.emit("messages.upsert", { type: "notify", messages: [withdrawal] });
  await persisted;
  finishGeneration();
  assert.match((await reply)[0], /autorización fue retirada/);
  assert.deepEqual(requests, [
    ["GET", "consent"], ["POST", "claim"], ["POST", "15"], ["POST", "consent"], ["POST", "release"]
  ]);
});

test("retrying a withdrawal after response loss keeps its identity and avoids a duplicate acknowledgement", async (t) => {
  const decisions = [];
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    decisions.push(JSON.parse(Buffer.concat(chunks)));
    if (decisions.length === 1) {
      res.destroy();
      return;
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data: { consentimiento_datos: false, duplicate: true } }));
  });
  const url = await listen(t, backend);
  const handler = tenantIngest("15", "synthetic", url, url);
  const message = { ...normalizeInbound(inbound()), body: "BAJA" };
  await handler(message, async () => assert.fail("Duplicate withdrawal acknowledgement"));
  assert.equal(decisions.length, 2);
  assert.deepEqual(decisions[1], decisions[0]);
  assert.equal(decisions[0].external_message_id, message.external_message_id);
  assert.equal(decisions[0].sent_at, message.sent_at);
});

test("the connector does not acknowledge a stale consent command", async (t) => {
  let payload;
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    payload = JSON.parse(Buffer.concat(chunks));
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data: { consentimiento_datos: false, stale: true } }));
  });
  const url = await listen(t, backend);
  const handler = tenantIngest("15", "synthetic", url, url);
  const message = { ...normalizeInbound(inbound()), body: "ACEPTO" };
  await handler(message, async () => assert.fail("Stale consent must not be acknowledged"));
  assert.equal(payload.sent_at, message.sent_at);
  assert.equal(payload.accepted, true);
});

test("durable admission submits the binding without starting generation or sending", async (t) => {
  const operations = [];
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    operations.push([req.url, chunks.length ? JSON.parse(Buffer.concat(chunks)) : null]);
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data: req.method === "GET"
      ? { consentimiento_datos: true }
      : { disposition: "accepted", turn_id: 1 } }));
  });
  const url = await listen(t, backend);
  const handler = tenantIngest("15", "synthetic", url, url);
  const message = normalizeInbound(inbound());
  let admitted = false;
  await handler(message, async () => assert.fail("Admission cannot send"), () => true, {
    accountKey: "a".repeat(64), recipientJid: "81@lid", admitted: () => { admitted = true; }
  });
  assert.equal(admitted, true);
  assert.equal(operations.length, 2);
  assert.match(operations[1][0], /turns\/enqueue$/);
  assert.deepEqual(operations[1][1], { ...message, account_key: "a".repeat(64), recipient_jid: "81@lid" });
});

test("a restored socket drains a persisted prepared turn without WhatsApp redelivery", { timeout: 5000 }, async (t) => {
  const operations = [];
  const completed = new EventEmitter();
  let providerId;
  const backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const operation = req.url.split("/").at(-1);
    const payload = JSON.parse(Buffer.concat(chunks));
    operations.push(operation);
    let data;
    if (operation === "next") {
      const account = createHash("sha256").update("12025550111@s.whatsapp.net").digest("hex");
      assert.deepEqual(payload, { account_key: account });
      data = { job: {
        turn_id: 5, state: "prepared", claimed: true, claim_token: "synthetic-claim-token",
        phone: "12025550138", recipient_jid: "81@lid", reply_body: "Respuesta preparada"
      } };
    } else if (operation === "begin-send") {
      providerId = payload.provider_message_id;
      assert.ok(providerId);
      data = { claimed: true, state: "sending" };
    } else if (operation === "receipts") {
      assert.deepEqual(payload.receipts, [{
        account_key: createHash("sha256").update("12025550111@s.whatsapp.net").digest("hex"),
        provider_message_id: providerId, recipient_jids: ["81@lid"], status: "read"
      }]);
      data = { applied: 1 };
    } else if (operation === "complete") {
      assert.equal(payload.provider_message_id, providerId);
      data = { state: "completed" };
    } else {
      assert.fail(`Unexpected operation ${operation}`);
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ data }));
    if (operation === "receipts") completed.emit("receipt");
    if (operation === "complete") completed.emit("acknowledged");
  });
  const url = await listen(t, backend);
  const ev = new EventEmitter();
  const connection = new WhatsAppConnection("unused", tenantIngest("15", "synthetic", url, url), async () => ({
    socket: {
      ev,
      user: { id: "12025550111:3@s.whatsapp.net" },
      sendMessage: async (jid, { text }, { messageId }) => {
        assert.equal(jid, "81@lid");
        assert.equal(text, "Respuesta preparada");
        assert.equal(messageId, providerId);
        const received = once(completed, "receipt");
        ev.emit("messages.update", [{
          key: { id: messageId, remoteJid: jid, fromMe: true },
          update: { status: WAMessageStatus.READ }
        }]);
        await received;
        return { key: { id: messageId } };
      }
    },
    saveCreds: async () => {}
  }), undefined, true);
  await connection.start();
  const acknowledged = once(completed, "acknowledged");
  ev.emit("connection.update", { connection: "open" });
  await acknowledged;
  ev.emit("connection.update", { connection: "close", lastDisconnect: { error: { output: { statusCode: 401 } } } });
  assert.deepEqual(operations, ["next", "begin-send", "receipts", "complete"]);
});

test("receipt normalization requires a direct outbound key and keeps only safe failure details", () => {
  const account = "a".repeat(64);
  const key = { id: "synthetic-id", remoteJid: "123:1@lid", remoteJidAlt: "12025550138@s.whatsapp.net", fromMe: true };
  const update = { status: WAMessageStatus.ERROR, messageStubParameters: ["463", "private provider detail"] };
  assert.deepEqual(normalizeReceipt(account, { key, update }), {
    account_key: account, provider_message_id: "synthetic-id",
    recipient_jids: ["123@lid", "12025550138@s.whatsapp.net"],
    status: "failed", failure_reason: "account_restricted"
  });
  assert.equal(normalizeReceipt(account, { key: { ...key, fromMe: false }, update }), undefined);
  assert.equal(normalizeReceipt(account, { key: { ...key, remoteJid: "123@g.us" }, update }), undefined);
  assert.equal(normalizeReceipt(account, { key, update: { status: WAMessageStatus.PENDING } }), undefined);
});

test("receipt buffering stays bounded and merges pending evidence without regression", async () => {
  const sent = [];
  let failures = 0;
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  const queue = new ReceiptBuffer(async receipts => {
    sent.push(receipts);
    if (sent.length === 1) await blocked;
  }, () => { failures++; });
  const receipt = (id, status) => ({ account_key: "a".repeat(64), provider_message_id: id,
    recipient_jids: ["123@lid"], status });
  queue.add([receipt("first", "sent")]);
  queue.add([receipt("pending", "read"), receipt("pending", "sent"),
    ...Array.from({ length: 530 }, (_, index) => receipt(String(index), "delivered"))]);
  release();
  await new Promise(setImmediate);
  assert.equal(failures, 1);
  assert.ok(sent.every(batch => batch.length <= 32));
  assert.equal(sent.flat().length, 513);
  assert.equal(sent.flat().find(event => event.provider_message_id === "pending").status, "read");
});
