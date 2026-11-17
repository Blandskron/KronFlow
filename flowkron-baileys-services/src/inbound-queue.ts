type Job = { sender: string; withdrawal: boolean; run: () => Promise<void> };

/** Bounded admission before expensive consent, CRM and model requests. */
export class InboundQueue {
  private pending: Job[] = [];
  private running = false;
  private withdrawals = 0;

  constructor(private readonly onError: () => void, private readonly capacity = 128) {}

  enqueue(sender: string, withdrawal: boolean, run: () => Promise<void>): boolean {
    if (withdrawal) {
      // A queued withdrawal supersedes this sender's ordinary work.
      this.pending = this.pending.filter(job => job.sender !== sender);
      if (this.pending.length >= this.capacity) {
        let ordinary = this.pending.length - 1;
        while (ordinary >= 0 && this.pending[ordinary].withdrawal) ordinary--;
        if (ordinary < 0) return false;
        this.pending.splice(ordinary, 1);
      }
    } else if (this.pending.filter(job => job.sender === sender).length >= 4 || this.pending.length >= this.capacity - 16) {
      return false;
    }
    const job = { sender, withdrawal, run };
    this.pending.push(job);
    void this.drain();
    return true;
  }

  clear() { this.pending = []; }
  get size() { return this.pending.length; }

  private async drain() {
    if (this.running) return;
    this.running = true;
    try {
      while (this.pending.length) {
        const preferred = this.pending.findIndex(job => job.withdrawal === (this.withdrawals < 4));
        const [job] = this.pending.splice(Math.max(preferred, 0), 1);
        this.withdrawals = job.withdrawal ? Math.min(this.withdrawals + 1, 4) : 0;
        try { await job.run(); } catch { this.onError(); }
      }
    } finally { this.running = false; }
  }
}
