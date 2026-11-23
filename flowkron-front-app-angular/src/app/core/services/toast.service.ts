import { Injectable, signal } from '@angular/core';

export type ToastTone = 'info' | 'success' | 'warning' | 'danger';

export interface ToastMessage {
  id: string;
  text: string;
  tone: ToastTone;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();
  readonly items = signal<readonly ToastMessage[]>([]);

  show(text: string, tone: ToastTone = 'info', durationMs = 4500): string {
    const id = crypto.randomUUID();
    this.items.update((list) => [...list.slice(-3), { id, text, tone }]);

    if (durationMs > 0) {
      const timer = setTimeout(() => this.dismiss(id), durationMs);
      this.timers.set(id, timer);
    }
    return id;
  }

  success(text: string, durationMs = 4000): string {
    return this.show(text, 'success', durationMs);
  }

  error(text: string, durationMs = 6000): string {
    return this.show(text, 'danger', durationMs);
  }

  info(text: string, durationMs = 4500): string {
    return this.show(text, 'info', durationMs);
  }

  dismiss(id: string): void {
    const timer = this.timers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(id);
    }
    this.items.update((list) => list.filter((item) => item.id !== id));
  }

  clear(): void {
    this.timers.forEach((timer) => clearTimeout(timer));
    this.timers.clear();
    this.items.set([]);
  }
}
