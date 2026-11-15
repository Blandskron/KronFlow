import type { WAMessage } from "baileys";

export function normalizeInbound(message: WAMessage) {
  const { key } = message;
  const jid = key.remoteJid;
  if (!jid || key.fromMe || !key.id || key.id.length > 180) return;

  const directPhone = /^([1-9]\d{6,14})@s\.whatsapp\.net$/;
  const match = directPhone.exec(jid) ||
    (/^\d+@lid$/.test(jid) && directPhone.exec(key.remoteJidAlt ?? ""));
  if (!match || jid.length > 180) return;

  const raw = message.message;
  const body = (raw?.conversation || raw?.extendedTextMessage?.text || "").trim();
  if (!body || body.length > 4000) return;
  const seconds = Number(message.messageTimestamp);
  const sentAt = new Date(seconds * 1000);
  if (seconds <= 0 || !Number.isFinite(sentAt.getTime())) return;

  return {
    external_message_id: `baileys:${match[1]}:${key.id}`,
    external_thread_id: match[1],
    phone: match[1],
    direction: "inbound",
    body,
    channel: "whatsapp",
    sent_at: sentAt.toISOString()
  } as const;
}

export function operationalIngest(env: NodeJS.ProcessEnv) {
  const base = env.OPERATIONAL_SERVICE_URL;
  const code = env.BAILEYS_INGEST_TENANT_CODE;
  const key = env.BAILEYS_INGEST_KEY;
  if (!code && !key) return;
  if (!base || !code || !key) throw new Error("Operational ingestion configuration is incomplete");

  const url = new URL("/api/v1/ingest/whatsapp/", base);
  const headers = { "X-Tenant-Code": code, "X-Ingest-Key": key };
  return async (message: NonNullable<ReturnType<typeof normalizeInbound>>) => {
    const consentUrl = new URL("consent", url);
    consentUrl.searchParams.set("phone", message.phone);
    const consent = await fetch(consentUrl, {
      headers,
      redirect: "error",
      signal: AbortSignal.timeout(5000)
    });
    if (!consent.ok) throw new Error("Could not verify consent");
    const decision: { consentimiento_datos?: unknown } = await consent.json();
    if (decision.consentimiento_datos !== true) return;
    const result = await fetch(new URL("message", url), {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(message),
      redirect: "error",
      signal: AbortSignal.timeout(5000)
    });
    if (!result.ok) throw new Error("Operational ingestion failed");
  };
}
