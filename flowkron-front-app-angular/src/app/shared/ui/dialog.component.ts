import { ChangeDetectionStrategy, Component, ElementRef, input, output, viewChild } from '@angular/core';

@Component({
  selector: 'flowkron-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog
      #dialogEl
      class="fk-dialog card"
      [attr.aria-labelledby]="titleId()"
      (close)="closed.emit()"
    >
      <header class="fk-dialog-header">
        <h2 [id]="titleId()">{{ title() }}</h2>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          aria-label="Cerrar diálogo"
          (click)="close()"
        >
          Cerrar
        </button>
      </header>
      <div class="fk-dialog-body">
        <ng-content />
      </div>
    </dialog>
  `,
  styles: `
    .fk-dialog {
      width: min(640px, calc(100% - 32px));
      padding: clamp(16px, 4vw, 28px);
      color: var(--foreground);
      line-height: 1.6;
    }

    .fk-dialog::backdrop {
      background: rgba(15, 7, 23, 0.68);
    }

    .fk-dialog-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-4);
      margin-bottom: var(--space-4);
    }

    h2 {
      margin: 0;
      font-size: var(--text-xl);
    }
  `
})
export class DialogComponent {
  readonly title = input.required<string>();
  readonly titleId = input<string>('flowkron-dialog-title');
  readonly closed = output<void>();

  private readonly dialogEl = viewChild.required<ElementRef<HTMLDialogElement>>('dialogEl');

  open(): void {
    const el = this.dialogEl().nativeElement;
    if (!el.open) {
      el.showModal();
    }
  }

  close(): void {
    const el = this.dialogEl().nativeElement;
    if (el.open) {
      el.close();
    }
  }
}
