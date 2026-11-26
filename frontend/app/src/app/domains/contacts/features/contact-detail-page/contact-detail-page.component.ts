import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Contact, ContactDetail, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { leadStages } from '@domains/leads/domain/lead.model';
import { ContactConsentComponent } from './contact-consent.component';
import { Observable, Subject, catchError, combineLatest, distinctUntilChanged, filter, finalize, map, of, shareReplay, startWith, switchMap, takeUntil, tap } from 'rxjs';

type DetailState =
  | { status: 'loading' }
  | { status: 'error'; message: string; retryable: boolean }
  | { status: 'ready'; contact: ContactDetail };

@Component({
  selector: 'kronflow-contact-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, ContactConsentComponent],
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
            @if (state.retryable) {
              <button class="btn btn-secondary" type="button" (click)="reloadDetail.next()">Reintentar</button>
            }
          }
          @case ('ready') {
            @let contact = renamed()?.id === state.contact.id ? renamed()! : state.contact;
            @let points = savedPoints()?.id === state.contact.id ? savedPoints()! : state.contact;
            <h1>{{ contact.full_name || 'Contacto sin nombre' }}</h1>
            @if (auth.hasPermission('crm.manage')) {
              <form class="rename" (submit)="$event.preventDefault(); rename(contact, name.value)">
                <label for="contact-full-name">Nombre del contacto</label>
                <input #name class="field" id="contact-full-name" [value]="contact.full_name" maxlength="180" required />
                <button class="btn btn-primary" type="submit" [disabled]="saving() || renameConflict()">Guardar nombre</button>
                @if (renameError()) { <p role="alert">{{ renameError() }}</p> }
                @if (renameConflict()) {
                  <button class="btn btn-secondary" type="button" (click)="reloadDetail.next()">Recargar ficha</button>
                }
              </form>
            }
            <dl class="card">
              <dt>Correo electrónico</dt><dd>{{ (points.normalized_email ?? points.email) || 'Sin correo' }}</dd>
              <dt>Teléfono</dt><dd>{{ (points.normalized_phone ?? points.phone) || 'Sin teléfono' }}</dd>
              <dt>Origen</dt><dd>{{ state.contact.source || 'Sin origen' }}</dd>
              <dt>Fecha de creación</dt><dd>{{ state.contact.created_at | date:'dd/MM/yyyy' }}</dd>
            </dl>
            @if (auth.hasPermission('crm.manage')) {
              <section class="points" aria-labelledby="contact-merge">
                <h2 id="contact-merge">Conciliar y fusionar identidad</h2>
                <form (submit)="$event.preventDefault(); mergeInto(contact.id, mergeTarget.value, mergeReason.value, mergeConfirm.checked)">
                  <label for="merge-target-id">ID de contacto destino
                    <input #mergeTarget class="field" id="merge-target-id" type="number" min="1" placeholder="Ej. 42" required />
                  </label>
                  <label for="merge-reason">Motivo
                    <input #mergeReason class="field" id="merge-reason" type="text" maxlength="240" value="manual_reconciliation" required />
                  </label>
                  <label for="merge-confirm">
                    <input #mergeConfirm id="merge-confirm" type="checkbox" required />
                    Confirmar fusión irreversible (conserva historial y supresiones)
                  </label>
                  <button class="btn btn-secondary" type="submit" [disabled]="merging()">Fusionar en destino</button>
                </form>
                @if (mergeNotice(); as mNotice) { <p [attr.role]="mNotice.error ? 'alert' : 'status'">{{ mNotice.message }}</p> }
              </section>
            }
            @if (auth.hasPermission('crm.manage') && state.contact.source === 'crm_manual') {
              <section class="points" aria-labelledby="contact-points">
                <h2 id="contact-points">Editar datos de contacto</h2>
                <form (submit)="$event.preventDefault(); updatePoints(points, email.value, phone.value)">
                  <label>Correo del contacto
                    <input #email class="field" type="email" maxlength="254" [value]="points.email ?? ''" />
                  </label>
                  <label>Teléfono del contacto
                    <input #phone class="field" type="tel" maxlength="80" placeholder="+56 9 1234 5678" [value]="points.phone ?? ''" />
                  </label>
                  <button class="btn btn-primary" type="submit" [disabled]="savingPoints() || pointsConflict()">Guardar datos de contacto</button>
                </form>
                @if (pointsNotice(); as notice) { <p [attr.role]="notice.error ? 'alert' : 'status'">{{ notice.message }}</p> }
                @if (pointsConflict()) {
                  <button class="btn btn-secondary" type="button" (click)="reloadDetail.next()">Recargar datos de contacto</button>
                }
              </section>
            }
            @if (auth.hasPermission('audit.read')) {
              <kronflow-contact-consent [contactId]="contact.id" />
            }
            <section aria-labelledby="contact-leads">
              <h2 id="contact-leads">Leads de este contacto</h2>
              @let leads = relatedLeads();
              @if (leads) {
                @for (lead of leads.items; track lead.id) {
                  <p><a [routerLink]="['/app/leads', lead.id]">Lead #{{ lead.id }} · {{ stageLabel(lead.lifecycle_status) }}</a></p>
                } @empty {
                  <p class="muted">Sin leads registrados.</p>
                  @if (auth.hasPermission('crm.manage')) {
                    <button class="btn btn-primary" type="button" [disabled]="startingLead()" (click)="startLead(contact.id)">
                      Iniciar seguimiento
                    </button>
                    @if (startLeadError()) { <p role="alert">{{ startLeadError() }}</p> }
                  }
                }
                @if (leads.total) {
                  <a routerLink="/app/leads" [queryParams]="{ contact_id: contact.id }">Ver seguimiento de leads</a>
                }
              } @else if (leads === null) {
                <p role="status">No pudimos consultar los leads.</p>
                <button class="btn btn-secondary" type="button" (click)="reloadLeads.next()">Reintentar leads</button>
              } @else { <p role="status">Consultando leads…</p> }
            </section>
            <section aria-labelledby="contact-conversations">
              <h2 id="contact-conversations">Conversaciones vinculadas</h2>
              @let threads = relatedConversations();
              @if (threads) {
                @for (thread of threads.items; track thread.id) {
                  <p><a routerLink="/app/conversations" [queryParams]="{ conversation: thread.id }">
                    {{ thread.last_message_at | date:'dd/MM/yyyy HH:mm' }} · {{ thread.channel }}
                  </a></p>
                } @empty { <p class="muted">Sin conversaciones vinculadas.</p> }
                @if (threads.total > threads.items.length) {
                  <a routerLink="/app/conversations" [queryParams]="{ contact_id: contact.id }">Ver todas las conversaciones</a>
                }
              } @else if (threads === null) {
                <p role="status">No pudimos consultar las conversaciones.</p>
                <button class="btn btn-secondary" type="button" (click)="reloadConversations.next()">Reintentar conversaciones</button>
              } @else { <p role="status">Consultando conversaciones…</p> }
            </section>
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
    .points { margin-block: 20px; }
    .points form { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }
    .points label { display: grid; gap: 4px; }
  `
})
export class ContactDetailPageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly leads = inject(LeadsApiService);
  private readonly conversations = inject(ConversationsApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly historyState = inject(Location).getState() as { contactSearch?: unknown } | null;

  readonly backState = { contactSearch: this.historyState?.contactSearch };
  readonly auth = inject(AuthService);
  readonly renamed = signal<Contact | null>(null);
  readonly savedPoints = signal<ContactDetail | null>(null);
  readonly savingPoints = signal(false);
  readonly pointsConflict = signal(false);
  readonly pointsNotice = signal<{ error: boolean; message: string } | null>(null);
  readonly saving = signal(false);
  readonly renameError = signal('');
  readonly renameConflict = signal(false);
  readonly startingLead = signal(false);
  readonly startLeadError = signal('');
  readonly merging = signal(false);
  readonly mergeNotice = signal<{ error: boolean; message: string } | null>(null);
  readonly reloadDetail = new Subject<void>();
  readonly reloadLeads = new Subject<void>();
  readonly reloadConversations = new Subject<void>();
  private readonly contactId$ = this.route.paramMap.pipe(map((params) => params.get('id') ?? ''), distinctUntilChanged());

  private readonly detail$ = combineLatest([this.contactId$, this.reloadDetail.pipe(startWith(undefined))]).pipe(
    tap(() => {
      this.renamed.set(null);
      this.renameError.set('');
      this.renameConflict.set(false);
      this.startLeadError.set('');
      this.savedPoints.set(null);
      this.pointsConflict.set(false);
      this.pointsNotice.set(null);
    }),
    switchMap(([id]) => this.contacts.get(id).pipe(
      map((contact): DetailState => ({ status: 'ready', contact })),
      catchError((error: HttpErrorResponse) => {
        if (error.status === 403) {
          return of<DetailState>({ status: 'error', retryable: false, message: 'No tienes permiso para consultar este contacto.' });
        }
        if (error.status === 404 || error.status === 422) {
          return of<DetailState>({ status: 'error', retryable: false, message: 'No encontramos este contacto en la empresa actual.' });
        }
        return of<DetailState>({ status: 'error', retryable: true, message: 'No pudimos consultar este contacto.' });
      }),
      startWith<DetailState>({ status: 'loading' })
    )),
    shareReplay({ bufferSize: 1, refCount: true })
  );
  readonly detail = toSignal(this.detail$, { requireSync: true });
  readonly relatedLeads = this.loadActivity(this.reloadLeads, (id) => this.leads.listLeads({ contact_id: id, limit: 5 }));
  readonly relatedConversations = this.loadActivity(this.reloadConversations,
    (id) => this.conversations.listConversations({ contact_id: id, limit: 5 }));

  stageLabel(id: string): string {
    return leadStages.find((stage) => stage.id === id)?.label ?? id;
  }

  updatePoints(contact: Contact, email: string, phone: string): void {
    if (this.savingPoints() || this.pointsConflict()) return;
    const points = { email: email.trim() || null, phone: phone.trim() || null };
    if (points.email === contact.email && points.phone === contact.phone) return;
    const routeId = this.route.snapshot.paramMap.get('id') ?? '';
    this.savingPoints.set(true);
    this.pointsNotice.set(null);
    this.contacts.updatePoints(contact, points).pipe(
      takeUntil(this.contactId$.pipe(filter((id) => id !== routeId))),
      takeUntilDestroyed(this.destroyRef), finalize(() => this.savingPoints.set(false))
    ).subscribe({
      next: (saved) => {
        this.savedPoints.set(saved);
        this.pointsNotice.set({ error: false, message: 'Datos de contacto guardados.' });
      },
      error: (error: HttpErrorResponse) => {
        this.pointsConflict.set(error.status === 409);
        const message = error.status === 409 ? 'Los datos cambiaron en otra sesión. Recarga la ficha para ver los valores vigentes.'
          : error.status === 422 ? 'Revisa el correo y usa un prefijo internacional en el teléfono.'
          : 'No pudimos guardar los datos de contacto.';
        this.pointsNotice.set({ error: true, message });
      }
    });
  }

  startLead(contactId: number): void {
    if (this.startingLead()) return;
    const routeId = this.route.snapshot.paramMap.get('id') ?? '';
    this.startingLead.set(true);
    this.startLeadError.set('');
    this.leads.start(contactId).pipe(
      takeUntil(this.contactId$.pipe(filter((id) => id !== routeId))),
      takeUntilDestroyed(this.destroyRef), finalize(() => this.startingLead.set(false))
    ).subscribe({
      next: ({ lead }) => { void this.router.navigate(['/app/leads', lead.id]); },
      error: () => this.startLeadError.set('No pudimos iniciar el seguimiento. Puedes reintentar.')
    });
  }

  rename(contact: Contact, name: string): void {
    const fullName = name.trim();
    if (this.saving() || this.renameConflict() || !fullName || fullName === contact.full_name) return;
    const currentId = this.route.snapshot.paramMap.get('id') ?? '';
    this.saving.set(true);
    this.renameError.set('');
    this.contacts.rename(contact.id, fullName, contact.full_name).pipe(
      takeUntil(this.contactId$.pipe(filter((id) => id !== currentId))),
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))
    ).subscribe({
      next: (saved) => this.renamed.set(saved),
      error: (error: HttpErrorResponse) => {
        this.renameConflict.set(error.status === 409);
        this.renameError.set(error.status === 409
          ? 'El nombre cambió en otra sesión. Recarga la ficha para ver el nombre actual.'
          : 'No pudimos guardar el nombre del contacto.');
      }
    });
  }

  mergeInto(sourceId: number, targetIdRaw: string, reason: string, confirmed: boolean): void {
    const targetId = Number(targetIdRaw);
    if (this.merging() || !confirmed || !Number.isSafeInteger(targetId) || targetId < 1 || targetId === sourceId) {
      this.mergeNotice.set({ error: true, message: 'Indica un ID destino válido distinto al actual y confirma la fusión.' });
      return;
    }
    this.merging.set(true);
    this.mergeNotice.set(null);
    this.contacts.merge(sourceId, targetId, reason.trim() || 'manual_reconciliation', true).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.merging.set(false))
    ).subscribe({
      next: () => { void this.router.navigate(['/app/contacts', targetId]); },
      error: (err: HttpErrorResponse) => {
        const msg = typeof err.error?.detail === 'string' ? err.error.detail : 'No pudimos completar la fusión de contactos.';
        this.mergeNotice.set({ error: true, message: msg });
      }
    });
  }

  private loadActivity<T>(reload: Observable<void>, load: (id: number) => Observable<T>) {
    return toSignal(combineLatest([this.detail$, reload.pipe(startWith(undefined))]).pipe(
      switchMap(([state]) => state.status !== 'ready' ? of(undefined) : load(state.contact.id).pipe(
        catchError(() => of(null)), startWith(undefined)
      ))
    ));
  }
}
