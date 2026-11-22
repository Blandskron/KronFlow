import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Contact, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { leadStages } from '@domains/leads/domain/lead.model';
import { catchError, finalize, forkJoin, map, of, shareReplay, startWith, switchMap, tap } from 'rxjs';

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
            @let contact = renamed()?.id === state.contact.id ? renamed()! : state.contact;
            <h1>{{ contact.full_name || 'Contacto sin nombre' }}</h1>
            @if (auth.hasPermission('crm.manage')) {
              <form class="rename" (submit)="$event.preventDefault(); rename(contact, name.value)">
                <label for="contact-full-name">Nombre del contacto</label>
                <input #name class="field" id="contact-full-name" [value]="contact.full_name" maxlength="180" required />
                <button class="btn btn-primary" type="submit" [disabled]="saving()">Guardar nombre</button>
                @if (renameError()) { <p role="alert">{{ renameError() }}</p> }
              </form>
            }
            <dl class="card">
              <dt>Correo electrónico</dt><dd>{{ state.contact.email || 'Sin correo' }}</dd>
              <dt>Teléfono</dt><dd>{{ state.contact.phone || 'Sin teléfono' }}</dd>
              <dt>Origen</dt><dd>{{ state.contact.source || 'Sin origen' }}</dd>
              <dt>Fecha de creación</dt><dd>{{ state.contact.created_at | date:'dd/MM/yyyy' }}</dd>
            </dl>
            @if (related(); as activity) {
              <section aria-labelledby="contact-leads">
                <h2 id="contact-leads">Leads de este contacto</h2>
                @if (activity.leads; as leads) {
                  @for (lead of leads.items; track lead.id) {
                    <p>Lead #{{ lead.id }} · {{ stageLabel(lead.lifecycle_status) }}</p>
                  } @empty { <p class="muted">Sin leads registrados.</p> }
                  @if (leads.total) {
                    <a routerLink="/app/leads" [queryParams]="{ contact_id: contact.id }">Ver seguimiento de leads</a>
                  }
                } @else { <p role="status">No pudimos consultar los leads.</p> }
              </section>
              <section aria-labelledby="contact-conversations">
                <h2 id="contact-conversations">Conversaciones vinculadas</h2>
                @if (activity.conversations; as threads) {
                  @for (thread of threads.items; track thread.id) {
                    <p><a routerLink="/app/conversations" [queryParams]="{ conversation: thread.id }">
                      {{ thread.last_message_at | date:'dd/MM/yyyy HH:mm' }} · {{ thread.channel }}
                    </a></p>
                  } @empty { <p class="muted">Sin conversaciones vinculadas.</p> }
                  @if (threads.total > threads.items.length) {
                    <a routerLink="/app/conversations" [queryParams]="{ contact_id: contact.id }">Ver todas las conversaciones</a>
                  }
                } @else { <p role="status">No pudimos consultar las conversaciones.</p> }
              </section>
            }
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
    .rename { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-block: 12px; }
    .rename input { width: min(20rem, 100%); }
  `
})
export class ContactDetailPageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly leads = inject(LeadsApiService);
  private readonly conversations = inject(ConversationsApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly historyState = inject(Location).getState() as { contactSearch?: unknown } | null;

  readonly backState = { contactSearch: this.historyState?.contactSearch };
  readonly auth = inject(AuthService);
  readonly renamed = signal<Contact | null>(null);
  readonly saving = signal(false);
  readonly renameError = signal('');
  private readonly detail$ = this.route.paramMap.pipe(
    tap(() => { this.renamed.set(null); this.renameError.set(''); }),
    switchMap((params) => this.contacts.get(params.get('id') ?? '').pipe(
      map((contact): DetailState => ({ status: 'ready', contact })),
      catchError((error: HttpErrorResponse) => of<DetailState>({
        status: 'error',
        message: error.status === 404 || error.status === 422
          ? 'No encontramos este contacto en la empresa actual.'
          : 'No pudimos consultar este contacto.'
      })),
      startWith<DetailState>({ status: 'loading' })
    )),
    shareReplay({ bufferSize: 1, refCount: true })
  );
  readonly detail = toSignal(this.detail$, { requireSync: true });
  readonly related = toSignal(this.detail$.pipe(
    switchMap((state) => state.status !== 'ready' ? of(null) : forkJoin({
      leads: this.leads.listLeads({ contact_id: state.contact.id, limit: 5 }).pipe(catchError(() => of(null))),
      conversations: this.conversations.listConversations({ contact_id: state.contact.id, limit: 5 })
        .pipe(catchError(() => of(null)))
    }).pipe(startWith(null)))
  ));

  stageLabel(id: string): string {
    return leadStages.find((stage) => stage.id === id)?.label ?? id;
  }

  rename(contact: Contact, name: string): void {
    const fullName = name.trim();
    if (this.saving() || !fullName || fullName === contact.full_name) return;
    this.saving.set(true);
    this.renameError.set('');
    this.contacts.rename(contact.id, fullName, contact.full_name).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))
    ).subscribe({
      next: (saved) => this.renamed.set(saved),
      error: (error: HttpErrorResponse) => this.renameError.set(error.status === 409
        ? 'El nombre cambió en otra sesión. Recarga la ficha antes de editarlo.'
        : 'No pudimos guardar el nombre del contacto.')
    });
  }
}
