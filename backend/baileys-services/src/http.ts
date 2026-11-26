import { timingSafeEqual } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import QRCode from "qrcode";
import {
  ConsentWithdrawnError,
  InactiveWorkspaceError,
  SessionNotConnectedError,
  type WhatsAppConnection,
} from "./connection.js";

const MAX_JSON_BODY_BYTES = 64 * 1024;

function json(response: ServerResponse, status: number, payload: object) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8"
  });
  response.end(JSON.stringify(payload));
}

class PayloadTooLargeError extends Error {}
class InvalidJsonError extends Error {}

async function readJsonBody(req: IncomingMessage, maxBytes = MAX_JSON_BODY_BYTES): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of req) {
    const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    total += buf.length;
    if (total > maxBytes) {
      throw new PayloadTooLargeError("Payload exceeds limit");
    }
    chunks.push(buf);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) throw new InvalidJsonError("Empty body");
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new InvalidJsonError("Malformed JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new InvalidJsonError("Expected JSON object");
  }
  return parsed as Record<string, unknown>;
}

type LegacyConnection = Pick<WhatsAppConnection, "start" | "snapshot">;
type TenantConnection = LegacyConnection &
  Pick<WhatsAppConnection, "stop"> &
  Partial<Pick<WhatsAppConnection, "sendHumanReply">>;

async function sessionResponse(connection: LegacyConnection, includeDiagnostics: boolean) {
  const before = connection.snapshot();
  const png = before.qr && before.status === "qr_pending" ? await QRCode.toDataURL(before.qr) : undefined;
  const current = connection.snapshot();
  const qr = current.status === "qr_pending" && current.qr === before.qr &&
    current.diagnostics?.qr_issued_at === before.diagnostics?.qr_issued_at ? png : undefined;
  return { status: current.status, qr, diagnostics: includeDiagnostics ? current.diagnostics : undefined };
}

export function createHttpServer(
  connection: LegacyConnection,
  token: string,
  resolveTenant?: (id: string) => TenantConnection
) {
  if (token.trim().length < 32) throw new Error("Set a private BAILEYS_INTERNAL_TOKEN of at least 32 characters");
  const expected = Buffer.from(`Bearer ${token}`);
  return createServer(async (req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      return json(res, 200, { status: "ok", service: "flowkron-baileys-services" });
    }

    const supplied = Buffer.from(req.headers.authorization ?? "");
    if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) {
      return json(res, 401, { error: "unauthorized" });
    }

    try {
      const tenant = /^\/internal\/baileys\/tenants\/([1-9][0-9]{0,14})\/session$/.exec(req.url ?? "");
      if (tenant && resolveTenant && ["POST", "GET", "DELETE"].includes(req.method ?? "")) {
        const session = resolveTenant(tenant[1]);
        if (req.method === "POST") await session.start();
        if (req.method === "DELETE") await session.stop();
        return json(res, 200, await sessionResponse(session, true));
      }
      const tenantMsg = /^\/internal\/baileys\/tenants\/([1-9][0-9]{0,14})\/messages$/.exec(req.url ?? "");
      if (tenantMsg && resolveTenant && req.method === "POST") {
        let body: Record<string, unknown>;
        try {
          body = await readJsonBody(req);
        } catch (error) {
          if (error instanceof PayloadTooLargeError) return json(res, 413, { error: "payload_too_large" });
          return json(res, 422, { error: "invalid_payload" });
        }
        const phone = typeof body.phone === "string" ? body.phone.trim() : "";
        const text = typeof body.text === "string" ? body.text.trim() : "";
        const digits = phone.replace(/\D/g, "");
        if (!digits || digits.length < 2 || digits.length > 15 || !text || text.length > 4096) {
          return json(res, 422, { error: "invalid_message_payload" });
        }
        const session = resolveTenant(tenantMsg[1]);
        if (!session.sendHumanReply) {
          return json(res, 503, { error: "whatsapp_session_unavailable" });
        }
        try {
          const result = await session.sendHumanReply(digits, text);
          return json(res, 200, { status: "sent", provider_message_id: result.provider_message_id ?? null });
        } catch (error) {
          if (error instanceof SessionNotConnectedError) {
            return json(res, 409, { error: "session_not_connected", sent: false, retryable: true });
          }
          if (error instanceof ConsentWithdrawnError) {
            return json(res, 409, { error: "consent_withdrawn", sent: false, retryable: false });
          }
          return json(res, 502, { error: "whatsapp_send_failed", sent: null, retryable: true });
        }
      }
      if (req.method === "POST" && req.url === "/internal/baileys/session/start") {
        await connection.start();
        const { status } = connection.snapshot();
        return json(res, status === "pairing_required" ? 409 : 202, { status });
      }
      if (req.method === "GET" && req.url === "/internal/baileys/session") {
        return json(res, 200, await sessionResponse(connection, false));
      }
      return json(res, 404, { error: "not_found" });
    } catch (error) {
      if (error instanceof InactiveWorkspaceError) return json(res, 409, { error: "workspace_inactive" });
      return json(res, 503, { error: "whatsapp_session_unavailable" });
    }
  });
}
