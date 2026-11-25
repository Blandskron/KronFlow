import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'kronflow-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="empty-state card glass-surface" aria-live="polite">
      <h3>{{ title() }}</h3>
      @if (description()) {
        <p class="muted">{{ description() }}</p>
      }
      <div class="empty-actions">
        <ng-content />
      </div>
    </section>
  `,
  styles: `
    .empty-state {
      display: grid;
      justify-items: center;
      text-align: center;
      gap: var(--space-2);
      padding: var(--space-8) var(--space-6);
    }

    h3 {
      margin: 0;
      font-size: var(--text-lg);
    }

    p {
      margin: 0;
      max-width: 48ch;
      line-height: 1.55;
    }

    .empty-actions:empty {
      display: none;
    }

    .empty-actions {
      margin-top: var(--space-2);
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: var(--space-2);
    }
  `
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly description = input<string>('');
}
