import { createHash } from "node:crypto";
import { rm } from "node:fs/promises";
import makeWASocket, { DisconnectReason, generateMessageIDV2, jidNormalizedUser, useMultiFileAuthState } from "baileys";
import pino from "pino";
import { normalizeInbound, type InboundHandler } from "./ingest.js";
import { InboundQueue } from "./inbound-queue.js";
import { normalizeReceipt, ReceiptBuffer } from "./receipts.js";

const logger = pino();
const retryLimit = 5;
const qrTimeout = 30_000;
const permanentDisconnects = new Map<number, DisconnectCause>([
  [DisconnectReason.loggedOut, "signed_out"],
  [DisconnectReason.badSession, "invalid_session"],
  [DisconnectReason.connectionReplaced, "replaced_session"],
  [DisconnectReason.forbidden, "provider_denied"],
  [DisconnectReason.multideviceMismatch, "device_mismatch"]
]);

async function openSocket(directory: string) {
  const { state, saveCreds } = await useMultiFileAuthState(directory);
  const socket = makeWASocket({
    auth: state,
    browser: ["Flowkron", "Chrome", "1.0.0"],
    logger: pino({ level: "silent" }),
    markOnlineOnConnect: false,
    syncFullHistory: false,
    qrTimeout,
    shouldSyncHistoryMessage: () => false
  });
  return { socket, saveCreds };
}

type ConnectionStatus = "disconnected" | "connecting" | "qr_pending" | "connected" | "pairing_required";
type ConnectionAction = "connect" | "scan" | "wait" | "retry" | "relink" | "none";
type DisconnectCause = "signed_out" | "invalid_session" | "replaced_session" | "provider_denied" |
  "device_mismatch" | "temporary" | "startup_failed" | "workspace_unavailable" | "manual";
type Socket = Awaited<ReturnType<typeof openSocket>>["socket"];
export class InactiveWorkspaceError extends Error {}
export class SessionNotConnectedError extends Error {}
export class ConsentWithdrawnError extends Error {}

function accountKey(socket: Socket) {
  const id = jidNormalizedUser(socket.user?.id);
  if (!id) return;
  return createHash("sha256").update(id).digest("hex");
}

async function sendDurableText(socket: Socket, jid: string, text: string, messageId: string) {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("WhatsApp provider acknowledgement timed out")), 60_000);
    timer.unref();
  });
  try {
    const sent = await Promise.race([socket.sendMessage(jid, { text }, { messageId }), timeout]);
    return { provider_message_id: sent?.key?.id ?? undefined };
  } finally {
    clearTimeout(timer);
  }
}

export class WhatsAppConnection {
  private status: ConnectionStatus = "disconnected";
  private statusChangedAt = new Date().toISOString();
  private readonly recentTransitions: { status: ConnectionStatus; changed_at: string }[] = [];
  private lastConnectedAt?: string;
  private disconnectCause?: DisconnectCause;
  private qr?: { value: string; issuedAt: number; expiresAt: number };
  private socket?: Socket;
  private starting?: Promise<void>;
  private stopping?: Promise<void>;
  private saving = Promise.resolve();
  private readonly inbound = new InboundQueue(() => logger.warn("Could not process an inbound WhatsApp message"));
  private readonly receipts = new ReceiptBuffer(
    async (receipts) => { await this.ingest?.recordReceipts?.(receipts); },
    () => logger.warn("Could not publish WhatsApp provider receipts")
  );
  private retry?: NodeJS.Timeout;
  private recoveryTimer?: NodeJS.Timeout;
  private recovering = false;
  private activeTurn?: { phone: string; interrupted: boolean };
  private nextRetryAt?: number;
  private retries = 0;
  private generation = 0;

  constructor(
    private readonly directory: string,
    private readonly ingest?: InboundHandler,
    private readonly connect = openSocket,
    private readonly canConnect?: () => Promise<boolean>,
    private readonly durableTurns = false
  ) {}

  snapshot() {
    const qr = this.status === "qr_pending" && this.qr && this.qr.expiresAt > Date.now() ? this.qr : undefined;
    const exhausted = this.status === "disconnected" && this.retries >= retryLimit && this.nextRetryAt === undefined;
    let action: ConnectionAction = "wait";
    if (this.status === "pairing_required") action = "relink";
    else if (this.status === "connected") action = "none";
    else if (qr) action = "scan";
    else if (this.status === "disconnected" && this.nextRetryAt === undefined) {
      action = this.disconnectCause && this.disconnectCause !== "manual" ? "retry" : "connect";
    }
    return {
      status: this.status,
      qr: qr?.value,
      diagnostics: {
        status_changed_at: this.statusChangedAt,
        recent_transitions: [...this.recentTransitions],
        last_connected_at: this.lastConnectedAt,
        disconnect_cause: this.disconnectCause,
        retry_attempts: this.retries,
        retry_limit: retryLimit,
        next_retry_at: this.nextRetryAt === undefined ? undefined : new Date(this.nextRetryAt).toISOString(),
        retry_exhausted: exhausted,
        next_action: action,
        qr_issued_at: this.qr ? new Date(this.qr.issuedAt).toISOString() : undefined,
        qr_expires_at: this.qr ? new Date(this.qr.expiresAt).toISOString() : undefined
      }
    };
  }

  start(): Promise<void> {
    return this.startAttempt(false);
  }

  async sendHumanReply(phone: string, text: string): Promise<{ provider_message_id: string | undefined }> {
    const digits = phone.replace(/\D/g, "");
    if (!digits) {
      throw new Error("Invalid WhatsApp recipient phone");
    }
    if (!this.socket || this.status !== "connected") {
      throw new SessionNotConnectedError("WhatsApp session is not connected");
    }
    if (this.inbound.hasWithdrawal(digits) || this.inbound.hasWithdrawal(phone)) {
      throw new ConsentWithdrawnError("Contact has a pending withdrawal");
    }
    const messageId = generateMessageIDV2(this.socket.user?.id);
    return sendDurableText(this.socket, `${digits}@s.whatsapp.net`, text, messageId);
  }

  private transition(status: ConnectionStatus) {
    if (this.status !== status) {
      this.status = status;
      this.statusChangedAt = new Date().toISOString();
      this.recentTransitions.unshift({ status, changed_at: this.statusChangedAt });
      if (this.recentTransitions.length > 8) this.recentTransitions.pop();
    }
  }

  private startAttempt(automatic: boolean): Promise<void> {
    if (this.stopping) return this.stopping;
    if (this.starting) return this.starting;
    if (this.socket || this.status === "pairing_required") return Promise.resolve();
    clearTimeout(this.retry);
    clearTimeout(this.recoveryTimer);
    this.retry = undefined;
    this.nextRetryAt = undefined;
    if (!automatic) this.retries = 0;
    this.transition("connecting");
    this.starting = this.attach(this.generation).catch((error: unknown) => {
      this.transition("disconnected");
      this.disconnectCause = error instanceof InactiveWorkspaceError ? "workspace_unavailable" : "startup_failed";
      throw error;
    }).finally(() => {
      this.starting = undefined;
    });
    return this.starting;
  }

  stop() {
    if (this.stopping) return this.stopping;
    this.generation++;
    this.stopping = this.disconnect().finally(() => {
      this.stopping = undefined;
    });
    return this.stopping;
  }

  private async disconnect() {
    await this.starting?.catch(() => undefined);
    clearTimeout(this.retry);
    clearTimeout(this.recoveryTimer);
    this.retry = undefined;
    this.nextRetryAt = undefined;
    const socket = this.socket;
    this.socket = undefined;
    this.qr = undefined;
    this.transition("disconnected");
    this.disconnectCause = "manual";
    this.retries = 0;
    this.inbound.discardNonWithdrawals();
    socket?.end(undefined);
    // Settle any queued write before clearing this tenant's credentials.
    await this.saving;
    await rm(this.directory, { recursive: true, force: true });
  }

  private async attach(generation: number) {
    if (this.canConnect && !await this.canConnect()) throw new InactiveWorkspaceError();
    if (generation !== this.generation) return;
    const { socket, saveCreds } = await this.connect(this.directory);
    if (generation !== this.generation) {
      socket.end(undefined);
      return;
    }
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
        if (this.status !== "connected") this.lastConnectedAt = new Date().toISOString();
        this.transition("connected");
        this.qr = undefined;
        this.disconnectCause = undefined;
        this.retries = 0;
        this.scheduleRecovery(socket, 0);
      } else if (connection === "close") {
        clearTimeout(this.recoveryTimer);
        this.socket = undefined;
        this.qr = undefined;
        const error = lastDisconnect?.error as { output?: { statusCode?: number } } | undefined;
        const code = error?.output?.statusCode;
        const permanentCause = code === undefined ? undefined : permanentDisconnects.get(code);
        if (permanentCause) {
          this.disconnectCause = permanentCause;
          this.transition("pairing_required");
        } else {
          this.disconnectCause = "temporary";
          this.transition("disconnected");
          this.scheduleRetry();
        }
      } else if (qr) {
        this.transition("qr_pending");
        if (this.qr?.value !== qr) {
          const issuedAt = Date.now();
          this.qr = { value: qr, issuedAt, expiresAt: issuedAt + qrTimeout - 1000 };
        }
      }
    });

    socket.ev.on("messages.upsert", ({ messages, type }) => {
      const ingest = this.ingest;
      const connected = () => this.socket === socket && this.status === "connected";
      if (type !== "notify" || !ingest || !connected()) return;
      for (const message of messages) {
        const inbound = normalizeInbound(message);
        if (!inbound || !message.key.remoteJid) continue;
        const jid = message.key.remoteJid;
        const command = inbound.body.toUpperCase();
        const kind = command === "BAJA" ? "withdraw" : command === "ACEPTO" ? "accept" : "message";
        const eventAt = Date.parse(inbound.sent_at);
        const account = this.durableTurns ? accountKey(socket) : undefined;
        if (this.durableTurns && kind === "message" && !account) {
          logger.warn("WhatsApp account identity unavailable for turn admission");
          continue;
        }
        const send = async (text: string) => {
          const sent = await socket.sendMessage(jid, { text });
          return { provider_message_id: sent?.key?.id ?? undefined };
        };
        const accepted = this.inbound.enqueue(inbound.phone, kind, async (isCurrent) => {
          const canReply = () => connected() && isCurrent() &&
            (kind === "withdraw" || !this.inbound.hasWithdrawal(inbound.phone));
          if (kind !== "withdraw" && !canReply()) return;
          await ingest(inbound, async (text) => {
            if (!canReply()) throw new Error("WhatsApp send interrupted");
            if (kind === "message") return send(text);
            // A slow acknowledgement must not block the next consent write.
            const queued = this.inbound.enqueue(inbound.phone, "message", async (ackIsCurrent) => {
              if (canReply() && ackIsCurrent()) await send(text);
            }, eventAt);
            if (!queued) logger.warn("WhatsApp consent acknowledgement capacity exceeded");
          }, canReply, account ? {
            accountKey: account, recipientJid: jid, admitted: () => this.scheduleRecovery(socket, 0)
          } : undefined);
        }, eventAt);
        if (accepted && kind === "withdraw" && this.activeTurn?.phone === inbound.phone) {
          this.activeTurn.interrupted = true;
        }
        if (!accepted) logger.warn("Inbound WhatsApp capacity exceeded");
      }
    });

    socket.ev.on("messages.update", updates => {
      if (this.socket !== socket || !this.durableTurns || !this.ingest?.recordReceipts) return;
      const account = accountKey(socket);
      if (!account) return;
      this.receipts.add(updates.flatMap(update => {
        const receipt = normalizeReceipt(account, update);
        return receipt ? [receipt] : [];
      }));
    });
  }

  private scheduleRecovery(socket: Socket, delay: number) {
    if (!this.durableTurns || !this.ingest?.recoverNext || this.recovering ||
        this.socket !== socket || this.status !== "connected") return;
    clearTimeout(this.recoveryTimer);
    this.recoveryTimer = setTimeout(() => void this.recover(socket), delay);
    this.recoveryTimer.unref();
  }

  private async recover(socket: Socket) {
    const recoverNext = this.ingest?.recoverNext;
    const account = accountKey(socket);
    if (!recoverNext || !account || this.socket !== socket || this.status !== "connected") return;
    this.recovering = true;
    let worked = false;
    try {
      worked = await recoverNext(account, async (phone, jid, run) => {
        const turn = { phone, interrupted: false };
        this.activeTurn = turn;
        const canReply = () => !turn.interrupted && !this.inbound.hasWithdrawal(phone) &&
          this.socket === socket && this.status === "connected" && accountKey(socket) === account;
        try {
          await run(async (text, messageId) => {
            if (!canReply()) throw new Error("WhatsApp durable send interrupted");
            if (!messageId) throw new Error("WhatsApp durable send requires a provider identity");
            return sendDurableText(socket, jid, text, messageId);
          }, canReply, generateMessageIDV2(socket.user?.id));
        } finally {
          this.activeTurn = undefined;
        }
      });
    } catch {
      logger.warn("Could not process a durable WhatsApp turn");
    } finally {
      this.recovering = false;
      if (this.socket) {
        this.scheduleRecovery(this.socket, worked ? 3000 : 12000 + Math.random() * 4000);
      }
    }
  }

  private scheduleRetry() {
    if (this.retries >= retryLimit) return;
    const delay = 1000 * 2 ** this.retries;
    this.nextRetryAt = Date.now() + delay;
    this.retry = setTimeout(() => {
      this.retries++;
      void this.startAttempt(true).catch((error: unknown) => {
        if (!(error instanceof InactiveWorkspaceError) && !this.stopping) this.scheduleRetry();
      });
    }, delay);
    this.retry.unref();
  }
}
