import type { WAMessage } from "baileys";
import type { ProviderReceipt } from "./receipts.js";
import { advanceTurn, processTurn, type SendText, type TurnSnapshot } from "./turn-pipeline.js";

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
    provider_message_id: key.id,
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


type Inbound = NonNullable<ReturnType<typeof normalizeInbound>>;
type Dispatch = { accountKey: string; recipientJid: string; admitted: () => void };
type Resume = (phone: string, jid: string,
  run: (reply: SendText, canReply: () => boolean, providerMessageId: string) => Promise<void>) => Promise<void>;
export type InboundHandler = ((
  message: Inbound, reply: SendText, canReply?: () => boolean, dispatch?: Dispatch
) => Promise<void>) & {
  recoverNext?: (accountKey: string, resume: Resume) => Promise<boolean>;
  recordReceipts?: (receipts: ProviderReceipt[]) => Promise<void>;
};

export function tenantIngest(
  tenant: string,
  token: string,
  operational: string,
  agent: string
): InboundHandler {
  const headers = { "X-Flowkron-Tenant": tenant, "X-Baileys-Token": token, "Content-Type": "application/json" };
  const base = new URL("/api/v1/ingest/whatsapp/", operational);
  const agentUrl = new URL(`/api/v1/agent/internal/whatsapp/${tenant}`, agent);
  const prompted = new Map<string, number>();
  const timeout = 70000;

  async function request(url: URL, payload?: object, requestTimeout = timeout) {
    const result = await fetch(url, {
      method: payload ? "POST" : "GET",
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
      redirect: "error",
      signal: AbortSignal.timeout(requestTimeout)
    });
    if (!result.ok) throw new Error(`WhatsApp pipeline HTTP ${result.status}`);
    const json = await result.json();
    return json.data ?? json;
  }

  const ingest: InboundHandler = async (message, reply, canReply = () => true, dispatch) => {
    const consentUrl = new URL("consent", base);
    const command = message.body.trim().toUpperCase();
    if (command === "ACEPTO" || command === "BAJA") {
      const decision = {
        phone: message.phone,
        accepted: command === "ACEPTO",
        policy_version: "flowkron-whatsapp-v1",
        external_message_id: message.external_message_id,
        sent_at: message.sent_at
      };
      // Transient downstream overload must not silently discard a withdrawal.
      for (let attempt = 0; ; attempt++) {
        try {
          const result = await request(consentUrl, decision, 5000);
          if (result.duplicate === true || result.stale === true) return;
          break;
        } catch (error) {
          if (command !== "BAJA" || attempt >= 2) throw error;
          await new Promise(resolve => setTimeout(resolve, 250 * 2 ** attempt));
        }
      }
      if (canReply()) {
        await reply(command === "ACEPTO"
          ? "Gracias. Ya puedes enviar tu consulta. Escribe BAJA si quieres retirar tu autorización."
          : "Tu autorización fue retirada. Si quieres volver a consultar, escribe ACEPTO.");
      }
      return;
    }

    if (!canReply()) return;
    consentUrl.searchParams.set("phone", message.phone);
    if (!(await request(consentUrl, undefined, 5000)).consentimiento_datos) {
      if (!canReply()) return;
      const now = Date.now();
      const last = prompted.get(message.phone);
      if (last && now - last < 86_400_000) return;
      if (prompted.size >= 1024) {
        const oldest = prompted.keys().next().value;
        if (oldest) prompted.delete(oldest);
      }
      await reply("Hola. Para responder tu consulta, el asistente de esta empresa guarda tu número y los mensajes de esta conversación. Escribe ACEPTO si autorizas ese uso o BAJA para retirarlo.");
      prompted.set(message.phone, now);
      return;
    }

    if (!canReply()) return;
    if (dispatch) {
      const admitted = await request(new URL("turns/enqueue", base), {
        ...message, account_key: dispatch.accountKey, recipient_jid: dispatch.recipientJid
      }, 5000);
      if (admitted.disposition === "accepted" || admitted.disposition === "duplicate") {
        dispatch.admitted();
        return;
      }
      if (admitted.disposition !== "legacy_untracked") throw new Error("Invalid WhatsApp turn admission");
    }
    await processTurn(message, reply, base, agentUrl, tenant, request, canReply);
  };
  ingest.recoverNext = async (accountKey, resume) => {
    const { job }: { job: (TurnSnapshot & { recipient_jid: string }) | null } = await request(
      new URL("turns/next", base), { account_key: accountKey }, 5000
    );
    if (!job) return false;
    if (!job.claimed || !job.phone || !job.claim_token || !job.turn_id) throw new Error("Invalid claimed WhatsApp job");
    await resume(job.phone, job.recipient_jid, async (reply, canReply, providerMessageId) => {
      const failure = await advanceTurn(job, reply, base, agentUrl, tenant, request, canReply, providerMessageId);
      if (failure) throw failure.error;
    });
    return true;
  };
  ingest.recordReceipts = async (receipts) => {
    await request(new URL("receipts", base), { receipts }, 5000);
  };
  return ingest;
}
