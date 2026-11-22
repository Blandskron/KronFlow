import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Contact, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { catchError, map, of, startWith, switchMap } from 'rxjs';

type DetailState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; contact: Contact };

@Component({
  selector: 'flowkron-contact-detail-page',
  standalone: true,
  imports: [RouterLink, DatePipe],
  template: `
    <section class="page-section">
      <a class="btn btn-secondary" routerLink="/app/contacts" queryParamsHandling="preserve" [state]="backState">
        Volver a Contactos
      </a>
      @if (detail(); as state) {
        @switch (state.status) {
          @case ('loading') { <p class="muted" role="status">Consultando contacto…</p> }
          @case ('error') {
            <h1>Contacto</h1>
            <p role="alert">{{ state.message }}</p>
          }
          @case ('ready') {
            <h1>{{ state.contact.full_name || 'Contacto sin nombre' }}</h1>
            <dl class="card">
              <dt>Correo electrónico</dt><dd>{{ state.contact.email || 'Sin correo' }}</dd>
              <dt>Teléfono</dt><dd>{{ state.contact.phone || 'Sin teléfono' }}</dd>
              <dt>Origen</dt><dd>{{ state.contact.source || 'Sin origen' }}</dd>
              <dt>Fecha de creación</dt><dd>{{ state.contact.created_at | date:'dd/MM/yyyy' }}</dd>
            </dl>
          }
        }
      }
    </section>
  `,
  styles: `
    .page-section { padding: clamp(18px, 3vw, 32px); }
    dl { margin: 0; max-width: 42rem; }
    dt { font-weight: 700; }
    dd { margin: 0 0 1rem; overflow-wrap: anywhere; }
    dd:last-child { margin-bottom: 0; }
  `
})
export class ContactDetailPageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly historyState = inject(Location).getState() as { contactSearch?: unknown } | null;

  readonly backState = { contactSearch: this.historyState?.contactSearch };
  readonly detail = toSignal(this.route.paramMap.pipe(
    switchMap((params) => this.contacts.get(params.get('id') ?? '').pipe(
      map((contact): DetailState => ({ status: 'ready', contact })),
      catchError((error: HttpErrorResponse) => of<DetailState>({
        status: 'error',
        message: error.status === 404 || error.status === 422
          ? 'No encontramos este contacto en la empresa actual.'
          : 'No pudimos consultar este contacto.'
      })),
      startWith<DetailState>({ status: 'loading' })
    ))
  ), { requireSync: true });
}
