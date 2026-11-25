import { timingSafeEqual } from "node:crypto";
import { createServer, type ServerResponse } from "node:http";
import QRCode from "qrcode";
import { InactiveWorkspaceError, type WhatsAppConnection } from "./connection.js";

function json(response: ServerResponse, status: number, payload: object) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8"
  });
  response.end(JSON.stringify(payload));
}

type LegacyConnection = Pick<WhatsAppConnection, "start" | "snapshot">;
type TenantConnection = LegacyConnection & Pick<WhatsAppConnection, "stop">;

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
