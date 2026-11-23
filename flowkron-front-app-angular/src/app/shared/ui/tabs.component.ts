import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export interface TabItem {
  id: string;
  label: string;
  badge?: string | number;
}

@Component({
  selector: 'flowkron-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="fk-tabs" role="tablist" [attr.aria-label]="ariaLabel()">
      @for (tab of tabs(); track tab.id; let idx = $index) {
        <button
          type="button"
          role="tab"
          class="fk-tab"
          [class.active]="activeId() === tab.id"
          [attr.aria-selected]="activeId() === tab.id"
          [attr.tabindex]="activeId() === tab.id ? 0 : -1"
          (click)="selected.emit(tab.id)"
          (keydown)="onKeydown($event, idx)"
        >
          <span>{{ tab.label }}</span>
          @if (tab.badge !== undefined && tab.badge !== '') {
            <span class="badge badge-neutral">{{ tab.badge }}</span>
          }
        </button>
      }
    </div>
  `,
  styles: `
    .fk-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-2);
      border-bottom: 1px solid var(--border);
      padding-bottom: var(--space-2);
    }

    .fk-tab {
      display: inline-flex;
      align-items: center;
      gap: var(--space-2);
      min-height: 40px;
      padding: var(--space-2) var(--space-4);
      border-radius: var(--radius-md);
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted-foreground);
      font-weight: 700;
      font-size: var(--text-sm);
      transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
    }

    .fk-tab:hover {
      background: var(--accent);
      color: var(--foreground);
    }

    .fk-tab.active {
      background: var(--selected);
      color: var(--primary);
      border-color: color-mix(in srgb, var(--primary) 30%, transparent);
    }
  `
})
export class TabsComponent {
  readonly tabs = input.required<readonly TabItem[]>();
  readonly activeId = input.required<string>();
  readonly ariaLabel = input<string>('Secciones');
  readonly selected = output<string>();

  onKeydown(event: KeyboardEvent, index: number): void {
    const items = this.tabs();
    if (!items.length) {
      return;
    }

    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight') {
      nextIndex = (index + 1) % items.length;
    } else if (event.key === 'ArrowLeft') {
      nextIndex = (index - 1 + items.length) % items.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = items.length - 1;
    }

    if (nextIndex !== null) {
      event.preventDefault();
      this.selected.emit(items[nextIndex].id);
    }
  }
}
