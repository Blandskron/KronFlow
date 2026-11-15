import { Component, ElementRef, input, viewChild } from '@angular/core';

@Component({
  selector: 'flowkron-legal-modal',
  standalone: true,
  template: `
    <dialog #modal class="modal card" aria-labelledby="legal-title">
      <header>
        <h2 id="legal-title">{{ title() }}</h2>
        <form method="dialog">
          <button class="btn btn-secondary" type="submit" autofocus>Cerrar</button>
        </form>
      </header>
      <p>{{ body() }}</p>
      <p>
        Flowkron opera con principios de trazabilidad, control de acceso y protección de
        datos para entornos empresariales. Esta versión mantiene textos base para reemplazo
        legal formal.
      </p>
    </dialog>
  `,
  styles: `
    .modal {
      width: min(620px, calc(100% - 32px));
      padding: clamp(16px, 4vw, 32px);
      color: var(--foreground);
      line-height: 1.65;
    }

    .modal::backdrop {
      background: rgba(15, 7, 23, 0.68);
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    h2 { margin: 0; }
    p { color: var(--muted-foreground); }
  `
})
export class LegalModalComponent {
  readonly title = input.required<string>();
  readonly body = input.required<string>();
  private readonly modal = viewChild.required<ElementRef<HTMLDialogElement>>('modal');

  show(): void {
    this.modal().nativeElement.showModal();
  }
}
