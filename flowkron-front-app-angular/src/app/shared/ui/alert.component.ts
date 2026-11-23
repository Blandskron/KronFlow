import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

@Component({
  selector: 'flowkron-alert',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div [class]="alertClass()" [attr.role]="role()">
      <div class="alert-body">
        @if (title()) {
          <strong>{{ title() }}</strong>
        }
        <div class="alert-message"><ng-content /></div>
      </div>
      @if (dismissible()) {
        <button
          type="button"
          class="alert-close"
          aria-label="Cerrar mensaje"
          (click)="dismissed.emit()"
        >
          ×
        </button>
      }
    </div>
  `,
  styles: `
    .fk-alert {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--space-3);
      padding: var(--space-3) var(--space-4);
      border-radius: var(--radius-md);
      border: 1px solid transparent;
      font-size: var(--text-sm);
      line-height: 1.5;
    }

    .alert-body {
      display: grid;
      gap: var(--space-1);
    }

    .fk-alert-info {
      background: var(--info-100);
      color: var(--info-text);
      border-color: color-mix(in srgb, var(--info-text) 22%, transparent);
    }

    .fk-alert-success {
      background: var(--success-100);
      color: var(--success-text);
      border-color: color-mix(in srgb, var(--success-text) 22%, transparent);
    }

    .fk-alert-warning {
      background: var(--warning-100);
      color: var(--warning-text);
      border-color: color-mix(in srgb, var(--warning-text) 22%, transparent);
    }

    .fk-alert-danger {
      background: var(--error-100);
      color: var(--error-text);
      border-color: color-mix(in srgb, var(--error-text) 22%, transparent);
    }

    .alert-close {
      border: 0;
      background: transparent;
      color: inherit;
      font-size: 1.25rem;
      line-height: 1;
      padding: 2px 6px;
      border-radius: var(--radius-sm);
    }
  `
})
export class AlertComponent {
  readonly tone = input<AlertTone>('info');
  readonly title = input<string>('');
  readonly dismissible = input<boolean>(false);
  readonly dismissed = output<void>();

  readonly alertClass = computed(() => `fk-alert fk-alert-${this.tone()}`);
  readonly role = computed(() => (this.tone() === 'danger' || this.tone() === 'warning' ? 'alert' : 'status'));
}
