import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'flowkron-page-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="page-header">
      <div class="page-header-copy">
        @if (eyebrow()) {
          <span class="eyebrow">{{ eyebrow() }}</span>
        }
        <h1>{{ title() }}</h1>
        @if (subtitle()) {
          <p class="muted">{{ subtitle() }}</p>
        }
      </div>
      <div class="page-header-actions">
        <ng-content />
      </div>
    </header>
  `,
  styles: `
    .page-header {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--space-4);
      margin-bottom: var(--space-6);
    }

    .page-header-copy {
      display: grid;
      gap: var(--space-1);
    }

    h1 {
      margin: 0;
      font-size: clamp(1.375rem, 2.4vw, 1.75rem);
      line-height: 1.2;
      letter-spacing: -0.02em;
    }

    p {
      margin: 0;
      font-size: var(--text-sm);
      max-width: 62ch;
      line-height: 1.5;
    }

    .page-header-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-2);
    }

    .page-header-actions:empty {
      display: none;
    }
  `
})
export class PageHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
  readonly eyebrow = input<string>('');
}
