import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { ContactConsent, ConsentEvidenceItem, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { Subject, catchError, map, of, startWith, switchMap } from 'rxjs';

type ConsentPage =
  | { status: 'idle' | 'loading' }
  | { status: 'error'; beforeId?: number; forbidden: boolean }
  | { status: 'ready'; beforeId?: number; data: ContactConsent };

@Component({
  selector: 'flowkron-contact-consent',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe],
  template: `
    <section aria-labelledby="contact-consent-title" class="card consent">
      <h2 id="contact-consent-title">Consentimiento de WhatsApp</h2>
      @let current = page();
      @switch (current.status) {
        @case ('idle') {
          <button class="btn btn-secondary" type="button" (click)="load.next(undefined)">Consultar consentimiento</button>
        }
        @case ('loading') { <p role="status">Consultando consentimiento…</p> }
        @case ('error') {
          @if (current.forbidden) {
            <p role="alert">No tienes permiso para consultar el consentimiento.</p>
          } @else {
            <p role="alert">No pudimos consultar el consentimiento.</p>
            <button class="btn btn-secondary" type="button" (click)="load.next(current.beforeId)">Reintentar consulta</button>
          }
        }
        @case ('ready') {
          @let consent = current.data;
          <p role="status"><strong>{{ labels[consent.state] }}</strong></p>
          @if (consent.decision_at || consent.authorized_from || consent.policy_version) {
            <dl>
              @if (consent.decision_at; as date) {
                <dt>Última decisión</dt><dd>{{ date | date:'dd/MM/yyyy HH:mm:ss' }}</dd>
              }
              @if (consent.authorized_from; as date) {
                <dt>Autorización desde</dt><dd>{{ date | date:'dd/MM/yyyy HH:mm:ss' }}</dd>
              }
              @if (consent.policy_version; as version) {
                <dt>Versión de política</dt><dd>{{ version }}</dd>
              }
            </dl>
          }
          @if (consent.state !== 'unlinked') {
            <h3>Historial de consentimiento</h3>
            @if (consent.items.length) {
              <ol>
                @for (event of consent.items; track event.id) {
                  <li>
                    <strong>{{ eventLabel(event) }}</strong>
                    @if (event.effective_at; as date) {
                      <span>Fecha de decisión {{ date | date:'dd/MM/yyyy HH:mm:ss' }}</span>
                    }
                    <span>Registro {{ event.recorded_at | date:'dd/MM/yyyy HH:mm:ss' }}</span>
                    @if (event.policy_version; as version) { <span>Política {{ version }}</span> }
                    @if (event.source === 'whatsapp_message') { <span>Mensaje de WhatsApp</span> }
                    @if (event.source === 'operational') { <span>Registro operativo</span> }
                  </li>
                }
              </ol>
            } @else { <p class="muted">Sin eventos en esta página.</p> }
            <div class="actions">
              @if (current.beforeId !== undefined) {
                <button class="btn btn-secondary" type="button" (click)="load.next(undefined)">Más recientes</button>
              }
              @if (consent.next_before_id; as cursor) {
                <button class="btn btn-secondary" type="button" (click)="load.next(cursor)">Ver eventos anteriores</button>
              }
            </div>
          }
        }
      }
    </section>
  `,
  styles: `
    .consent { margin-block: 20px; max-width: 42rem; }
    dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; }
    dt { font-weight: 700; }
    dd { margin: 0; }
    li + li { margin-top: 12px; }
    li span { display: block; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  `
})
export class ContactConsentComponent {
  private readonly api = inject(ContactsApiService);
  readonly contactId = input.required<number>();
  readonly load = new Subject<number | undefined>();
  readonly labels: Record<ContactConsent['state'], string> = {
    unlinked: 'Sin vínculo de WhatsApp',
    unrecorded: 'Sin decisión registrada',
    granted: 'Autorización vigente',
    not_granted: 'Sin autorización vigente'
  };

  readonly page = toSignal(toObservable(this.contactId).pipe(
    switchMap((id) => this.load.pipe(
      switchMap((beforeId) => this.api.whatsappConsent(id, beforeId).pipe(
        map((data): ConsentPage => ({ status: 'ready', beforeId, data })),
        catchError((error: HttpErrorResponse) =>
          of<ConsentPage>({ status: 'error', beforeId, forbidden: error.status === 403 })),
        startWith<ConsentPage>({ status: 'loading' })
      )),
      startWith<ConsentPage>({ status: 'idle' })
    ))
  ), { initialValue: { status: 'idle' } });

  eventLabel(event: ConsentEvidenceItem): string {
    if (event.kind === 'prior_withdrawal') return 'Baja de un periodo anterior';
    if (event.accepted === true) return 'Autorización registrada';
    if (event.accepted === false) return 'Denegación o baja registrada';
    return 'Decisión registrada';
  }
}
