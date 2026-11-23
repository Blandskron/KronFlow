import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ToastService } from '@core/services/toast.service';

@Component({
  selector: 'flowkron-toast-container',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toast-region" aria-live="polite" aria-atomic="false">
      @for (toast of toasts.items(); track toast.id) {
        <div
          class="toast card"
          [class]="'toast card toast-' + toast.tone"
          [attr.role]="toast.tone === 'danger' || toast.tone === 'warning' ? 'alert' : 'status'"
        >
          <span>{{ toast.text }}</span>
          <button
            type="button"
            class="toast-close"
            aria-label="Cerrar notificación"
            (click)="toasts.dismiss(toast.id)"
          >
            ×
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .toast-region {
      position: fixed;
      right: var(--space-4);
      bottom: var(--space-4);
      z-index: var(--z-toast);
      display: grid;
      gap: var(--space-2);
      width: min(380px, calc(100vw - 32px));
      pointer-events: none;
    }

    .toast {
      pointer-events: auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-3);
      padding: var(--space-3) var(--space-4);
      font-size: var(--text-sm);
      font-weight: 600;
      animation: fk-fade-in var(--duration-normal) var(--ease-standard);
    }

    .toast-info {
      background: var(--info-100);
      color: var(--info-text);
    }

    .toast-success {
      background: var(--success-100);
      color: var(--success-text);
    }

    .toast-warning {
      background: var(--warning-100);
      color: var(--warning-text);
    }

    .toast-danger {
      background: var(--error-100);
      color: var(--error-text);
    }

    .toast-close {
      border: 0;
      background: transparent;
      color: inherit;
      font-size: 1.25rem;
      line-height: 1;
      min-width: 32px;
      min-height: 32px;
      border-radius: var(--radius-sm);
    }
  `
})
export class ToastContainerComponent {
  readonly toasts = inject(ToastService);
}
