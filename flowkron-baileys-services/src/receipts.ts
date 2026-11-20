import { jidNormalizedUser, NACK_REASONS, SERVER_ERROR_CODES, WAMessageStatus, type WAMessageUpdate } from "baileys";

const priority = { sent: 1, failed: 2, delivered: 3, read: 4 };

export interface ProviderReceipt {
  account_key: string;
  provider_message_id: string;
  recipient_jids: string[];
  status: keyof typeof priority;
  failure_reason?: "provider_rejected" | "account_restricted" | "connection_invalid";
}

export function normalizeReceipt(account: string, { key, update }: WAMessageUpdate): ProviderReceipt | undefined {
  if (key.fromMe !== true || !key.id || key.id.length > 220) return;
  const direct = /^[0-9]+@(s\.whatsapp\.net|lid)$/;
  const primary = jidNormalizedUser(key.remoteJid ?? undefined);
  if (!direct.test(primary) || primary.length > 180) return;
  const alternate = jidNormalizedUser(key.remoteJidAlt ?? undefined);
  const recipients = [primary];
  if (alternate !== primary && direct.test(alternate) && alternate.length <= 180) recipients.push(alternate);
  const receipt = { account_key: account, provider_message_id: key.id, recipient_jids: recipients };
  switch (update.status) {
    case WAMessageStatus.SERVER_ACK: return { ...receipt, status: "sent" };
    case WAMessageStatus.DELIVERY_ACK: return { ...receipt, status: "delivered" };
    case WAMessageStatus.READ:
    case WAMessageStatus.PLAYED: return { ...receipt, status: "read" };
    case WAMessageStatus.ERROR: {
      const code = update.messageStubParameters?.[0];
      const failure_reason = code === String(NACK_REASONS.SenderReachoutTimelocked) ? "account_restricted"
        : code === SERVER_ERROR_CODES.SmaxInvalid ? "connection_invalid" : "provider_rejected";
      return { ...receipt, status: "failed", failure_reason };
    }
    default: return undefined;
  }
}

export class ReceiptBuffer {
  private pending = new Map<string, ProviderReceipt>();
  private flushing = false;

  constructor(
    private readonly publish: (receipts: ProviderReceipt[]) => Promise<void>,
    private readonly onError: () => void
  ) {}

  add(receipts: ProviderReceipt[]) {
    let overflow = false;
    for (const receipt of receipts) {
      const key = JSON.stringify([receipt.account_key, receipt.provider_message_id, ...receipt.recipient_jids]);
      const existing = this.pending.get(key);
      if (existing && priority[existing.status] >= priority[receipt.status]) continue;
      if (!existing && this.pending.size >= 512) {
        overflow = true;
        continue;
      }
      this.pending.set(key, receipt);
    }
    if (overflow) this.onError();
    void this.flush();
  }

  private async flush() {
    if (this.flushing) return;
    this.flushing = true;
    try {
      while (this.pending.size) {
        const batch = [...this.pending.entries()].slice(0, 32);
        for (const [key] of batch) this.pending.delete(key);
        const receipts = batch.map(([, receipt]) => receipt);
        for (let attempt = 0; ; attempt++) {
          try {
            await this.publish(receipts);
            break;
          } catch {
            if (attempt >= 2) {
              this.onError();
              break;
            }
            await new Promise(resolve => setTimeout(resolve, 250 * 2 ** attempt));
          }
        }
      }
    } finally {
      this.flushing = false;
    }
  }
}
