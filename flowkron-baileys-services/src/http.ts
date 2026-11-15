import { timingSafeEqual } from "node:crypto";
import { createServer, type ServerResponse } from "node:http";
import QRCode from "qrcode";
import type { WhatsAppConnection } from "./connection.js";

function json(response: ServerResponse, status: number, payload: object) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8"
  });
  response.end(JSON.stringify(payload));
}

type LegacyConnection = Pick<WhatsAppConnection, "start" | "snapshot">;
type TenantConnection = LegacyConnection & Pick<WhatsAppConnection, "stop">;

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
        const { status, qr } = session.snapshot();
        return json(res, 200, { status, qr: qr ? await QRCode.toDataURL(qr) : undefined });
      }
      if (req.method === "POST" && req.url === "/internal/baileys/session/start") {
        await connection.start();
        const { status } = connection.snapshot();
        return json(res, status === "pairing_required" ? 409 : 202, { status });
      }
      if (req.method === "GET" && req.url === "/internal/baileys/session") {
        const { status, qr } = connection.snapshot();
        return json(res, 200, { status, qr: qr ? await QRCode.toDataURL(qr) : undefined });
      }
      return json(res, 404, { error: "not_found" });
    } catch {
      return json(res, 503, { error: "whatsapp_session_unavailable" });
    }
  });
}
