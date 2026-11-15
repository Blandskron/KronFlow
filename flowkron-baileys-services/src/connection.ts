import { rm } from "node:fs/promises";
import makeWASocket, { DisconnectReason, useMultiFileAuthState } from "baileys";
import pino from "pino";
import { normalizeInbound, type InboundHandler } from "./ingest.js";

const logger = pino();
const permanentDisconnects: ReadonlySet<number> = new Set([
  DisconnectReason.loggedOut,
  DisconnectReason.badSession,
  DisconnectReason.connectionReplaced,
  DisconnectReason.forbidden,
  DisconnectReason.multideviceMismatch
]);

async function openSocket(directory: string) {
  const { state, saveCreds } = await useMultiFileAuthState(directory);
  const socket = makeWASocket({
    auth: state,
    browser: ["Flowkron", "Chrome", "1.0.0"],
    logger: pino({ level: "silent" }),
    markOnlineOnConnect: false,
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false
  });
  return { socket, saveCreds };
}

type ConnectionStatus = "disconnected" | "connecting" | "qr_pending" | "connected" | "pairing_required";

export class WhatsAppConnection {
  private status: ConnectionStatus = "disconnected";
  private qr?: string;
  private socket?: Awaited<ReturnType<typeof openSocket>>["socket"];
  private starting?: Promise<void>;
  private stopping?: Promise<void>;
  private saving = Promise.resolve();
  private forwarding = Promise.resolve();
  private retry?: NodeJS.Timeout;
  private retries = 0;

  constructor(
    private readonly directory: string,
    private readonly ingest?: InboundHandler,
    private readonly connect = openSocket
  ) {}

  snapshot() {
    return { status: this.status, qr: this.qr };
  }

  start(): Promise<void> {
    if (this.stopping) return this.stopping.then(() => this.start());
    if (this.starting) return this.starting;
    if (this.socket || this.status === "pairing_required") return Promise.resolve();
    clearTimeout(this.retry);
    this.retry = undefined;
    this.status = "connecting";
    this.starting = this.attach().catch((error: unknown) => {
      this.status = "disconnected";
      throw error;
    }).finally(() => {
      this.starting = undefined;
    });
    return this.starting;
  }

  stop() {
    if (this.stopping) return this.stopping;
    this.stopping = this.disconnect().finally(() => {
      this.stopping = undefined;
    });
    return this.stopping;
  }

  private async disconnect() {
    await this.starting?.catch(() => undefined);
    clearTimeout(this.retry);
    this.retry = undefined;
    const socket = this.socket;
    this.socket = undefined;
    this.qr = undefined;
    this.status = "disconnected";
    this.retries = 0;
    socket?.end(undefined);
    // Settle any queued write before clearing this tenant's credentials.
    await this.saving;
    await rm(this.directory, { recursive: true, force: true });
  }

  private async attach() {
    const { socket, saveCreds } = await this.connect(this.directory);
    this.socket = socket;

    socket.ev.on("creds.update", () => {
      if (this.socket !== socket) return;
      this.saving = this.saving.then(() => saveCreds()).catch(() => {
        logger.error("Could not persist WhatsApp credentials");
      });
    });

    socket.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
      if (this.socket !== socket) return;
      if (connection === "open") {
        this.status = "connected";
        this.qr = undefined;
        this.retries = 0;
      } else if (connection === "close") {
        this.socket = undefined;
        this.qr = undefined;
        const error = lastDisconnect?.error as { output?: { statusCode?: number } } | undefined;
        const code = error?.output?.statusCode;
        if (code !== undefined && permanentDisconnects.has(code)) {
          this.status = "pairing_required";
        } else {
          this.status = "disconnected";
          this.scheduleRetry();
        }
      } else if (qr) {
        this.status = "qr_pending";
        this.qr = qr;
      }
    });

    socket.ev.on("messages.upsert", ({ messages, type }) => {
      if (type !== "notify" || !this.ingest) return;
      for (const message of messages) {
        const inbound = normalizeInbound(message);
        if (!inbound || !message.key.remoteJid) continue;
        const jid = message.key.remoteJid;
        this.forwarding = this.forwarding.then(async () => {
          if (this.socket !== socket || this.status !== "connected") return;
          await this.ingest?.(inbound, async (text) => {
            if (this.socket !== socket || this.status !== "connected") throw new Error("Session disconnected");
            await socket.sendMessage(jid, { text });
          });
        }).catch(() => {
          logger.warn("Could not process an inbound WhatsApp message");
        });
      }
    });
  }

  private scheduleRetry() {
    if (this.retries >= 5) return;
    const delay = 1000 * 2 ** this.retries++;
    this.retry = setTimeout(() => {
      void this.start().catch(() => this.scheduleRetry());
    }, delay);
    this.retry.unref();
  }
}
