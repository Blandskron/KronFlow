export type InboundKind = "message" | "accept" | "withdraw";
type Job = {
  sender: string;
  kind: InboundKind;
  run: (isCurrent: () => boolean) => Promise<void>;
  eventAt?: number;
  interrupted?: boolean;
};

/** One conversation job and one consent write at a time per connection. */
export class InboundQueue {
  private pending: Job[] = [];
  private activeMessage?: Job;
  private activeConsent?: Job;
  private withdrawals = 0;

  constructor(private readonly onError: () => void, private readonly capacity = 128) {}

  enqueue(sender: string, kind: InboundKind, run: Job["run"], eventAt?: number): boolean {
    if (kind === "withdraw") {
      const superseded = (job: Job) => job.sender === sender &&
        (eventAt === undefined || job.eventAt === undefined || job.eventAt <= eventAt);
      const pending = this.pending.filter(job => !superseded(job));
      if (pending.length >= this.capacity) {
        let discard = pending.length - 1;
        while (discard >= 0 && pending[discard].kind === "withdraw") discard--;
        if (discard < 0) return false;
        pending.splice(discard, 1);
      }
      this.pending = pending;
      if (this.activeMessage && superseded(this.activeMessage)) this.activeMessage.interrupted = true;
      if (this.activeConsent?.kind === "accept" && superseded(this.activeConsent)) {
        this.activeConsent.interrupted = true;
      }
    } else if (this.pending.filter(job => job.sender === sender).length >= 4 || this.pending.length >= this.capacity - 16) {
      return false;
    }
    this.pending.push({ sender, kind, run, eventAt });
    this.drain();
    return true;
  }

  discardNonWithdrawals() {
    this.pending = this.pending.filter(job => job.kind === "withdraw");
  }

  get size() { return this.pending.length; }

  hasWithdrawal(sender: string) {
    return (this.activeConsent?.kind === "withdraw" && this.activeConsent.sender === sender) ||
      this.pending.some(job => job.kind === "withdraw" && job.sender === sender);
  }

  private drain() {
    if (!this.activeConsent) {
      const withdrawal = this.pending.findIndex(job => job.kind === "withdraw");
      const acceptance = this.withdrawals >= 4 || withdrawal < 0
        ? this.pending.findIndex((job, index) => job.kind === "accept" &&
            this.activeMessage?.sender !== job.sender &&
            !this.pending.some((other, position) => other.sender === job.sender && position < index))
        : -1;
      const index = acceptance >= 0 ? acceptance : withdrawal;
      if (index >= 0) {
        const [job] = this.pending.splice(index, 1);
        this.activeConsent = job;
        this.withdrawals = job.kind === "withdraw" ? Math.min(this.withdrawals + 1, 4) : 0;
        void this.execute(job).finally(() => {
          this.activeConsent = undefined;
          this.drain();
        });
      }
    }
    if (!this.activeMessage) {
      const index = this.pending.findIndex((job, index) => job.kind === "message" &&
        this.activeConsent?.sender !== job.sender &&
        !this.pending.some((other, position) => other.kind !== "message" &&
          other.sender === job.sender && position < index));
      if (index >= 0) {
        const [job] = this.pending.splice(index, 1);
        this.activeMessage = job;
        void this.execute(job).finally(() => {
          this.activeMessage = undefined;
          this.drain();
        });
      }
    }
  }

  private async execute(job: Job) {
    try { await job.run(() => !job.interrupted); } catch { this.onError(); }
  }
}
