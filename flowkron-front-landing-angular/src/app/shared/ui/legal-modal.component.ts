import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'flowkron-legal-modal',
  standalone: true,
  template: `
    @if (open) {
      <div class="modal-backdrop" (click)="close.emit()">
        <section class="modal card" (click)="$event.stopPropagation()">
          <header>
            <h2>{{ title }}</h2>
            <button class="icon-btn" type="button" aria-label="Cerrar" (click)="close.emit()">×</button>
          </header>
          <div class="content">
            <p>{{ body }}</p>
            <p>
              Flowkron opera con principios de trazabilidad, control de acceso y proteccion de
              datos para entornos empresariales. Esta version mantiene textos base para reemplazo
              legal formal.
            </p>
          </div>
        </section>
      </div>
    }
  `,
  styles: [
    `
      .modal-backdrop {
        position: fixed;
        inset: 0;
        z-index: 100;
        background: rgba(2, 6, 23, 0.54);
        display: grid;
        place-items: center;
        padding: 24px;
      }

      .modal {
        width: min(620px, 100%);
        padding: 24px;
      }

      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 12px;
      }

      h2 {
        margin: 0;
        font-size: 24px;
      }

      .content {
        color: var(--muted-foreground);
        line-height: 1.7;
      }
    `
  ]
})
export class LegalModalComponent {
  @Input({ required: true }) title = '';
  @Input({ required: true }) body = '';
  @Input() open = false;
  @Output() readonly close = new EventEmitter<void>();
}
