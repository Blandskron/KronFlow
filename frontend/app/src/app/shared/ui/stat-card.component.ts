import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type StatTone = 'default' | 'primary' | 'success' | 'warning' | 'danger';

@Component({
  selector: 'kronflow-stat-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <article [class]="cardClass()">
      <span class="stat-label muted">{{ label() }}</span>
      <strong class="stat-value">{{ value() }}</strong>
      @if (hint()) {
        <small class="stat-hint muted">{{ hint() }}</small>
      }
    </article>
  `,
  styles: `
    .stat-card {
      display: grid;
      gap: var(--space-1);
      padding: var(--space-5);
    }

    .stat-label {
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .stat-value {
      font-family: var(--font-display);
      font-variant-numeric: tabular-nums;
      font-size: clamp(1.5rem, 3vw, 2rem);
      line-height: 1.15;
      letter-spacing: -0.03em;
    }

    .stat-hint {
      font-size: var(--text-xs);
    }

    .stat-tone-primary .stat-value {
      color: var(--primary);
    }

    .stat-tone-success .stat-value {
      color: var(--success-text);
    }

    .stat-tone-warning .stat-value {
      color: var(--warning-text);
    }

    .stat-tone-danger .stat-value {
      color: var(--error-text);
    }
  `
})
export class StatCardComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  readonly hint = input<string>('');
  readonly tone = input<StatTone>('default');

  readonly cardClass = computed(() => `card glass-surface stat-card stat-tone-${this.tone()}`);
}
