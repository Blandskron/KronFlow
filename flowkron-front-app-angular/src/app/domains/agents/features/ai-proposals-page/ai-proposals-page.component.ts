import { DatePipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AIProposalItem, AIProposalsApiService } from '@domains/agents/data-access/ai-proposals-api.service';

@Component({
  selector: 'flowkron-ai-proposals-page',
  standalone: true,
  imports: [DatePipe, JsonPipe],
  template: `
    <section class="page-section">
      <header class="heading">
        <div>
          <h1>Revisión de propuestas IA</h1>
          <p class="muted">Aprueba, rechaza o ejecuta acciones tipadas propuestas por el agente.</p>
        </div>
        <button class="btn btn-secondary" type="button" [disabled]="loading()" (click)="reload()">
          {{ loading() ? 'Actualizando…' : 'Actualizar' }}
        </button>
      </header>

      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-block:16px" role="group" aria-label="Filtrar por estado">
        @for (st of statuses; track st.id) {
          <button class="btn btn-secondary" type="button" [attr.aria-pressed]="statusFilter() === st.id" (click)="setStatus(st.id)">
            {{ st.label }}
          </button>
        }
      </div>

      @if (notice(); as msg) {
        <p class="muted" [attr.role]="msg.error ? 'alert' : 'status'" style="margin-bottom:12px">{{ msg.text }}</p>
      }

      @if (loading() && !items().length) {
        <p class="muted" role="status">Cargando propuestas…</p>
      } @else if (!items().length) {
        <p class="muted" role="status">No hay propuestas en este estado.</p>
      } @else {
        <div style="display:grid;gap:12px">
          @for (item of items(); track item.id) {
            <article class="card glass-surface" style="padding:16px;display:grid;gap:8px">
              <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:center">
                <strong>#{{ item.id }} · {{ item.action_type }}</strong>
                <span class="badge badge-info">{{ item.status }} · v{{ item.proposal_version }}</span>
              </div>
              <small class="muted">
                Recurso: {{ item.resource_type }} #{{ item.resource_id }} · Propuesto por {{ item.proposed_by }}
                · Expira {{ item.expires_at | date:'short' }}
              </small>
              <pre style="margin:0;font-size:0.85rem;white-space:pre-wrap">{{ item.arguments | json }}</pre>
              @if (canManage()) {
                <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">
                  @if (item.status === 'pending') {
                    <button class="btn btn-primary" type="button" [disabled]="busy()" (click)="approve(item)">Aprobar</button>
                    <button class="btn btn-secondary" type="button" [disabled]="busy()" (click)="reject(item)">Rechazar</button>
                  }
                  @if (item.status === 'approved') {
                    <button class="btn btn-primary" type="button" [disabled]="busy()" (click)="execute(item)">Ejecutar efecto</button>
                  }
                </div>
              }
            </article>
          }
        </div>
      }
    </section>
  `
})
export class AIProposalsPageComponent implements OnInit {
  private readonly api = inject(AIProposalsApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly items = signal<AIProposalItem[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly statusFilter = signal('pending');
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly statuses = [
    { id: 'pending', label: 'Pendientes' },
    { id: 'approved', label: 'Aprobadas' },
    { id: 'executed', label: 'Ejecutadas' },
    { id: 'rejected', label: 'Rechazadas' },
    { id: 'expired', label: 'Expiradas' }
  ];

  ngOnInit(): void {
    this.reload();
  }

  setStatus(status: string): void {
    this.statusFilter.set(status);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.list(this.statusFilter()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (page) => {
        this.items.set(page.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.notice.set({ error: true, text: 'No pudimos cargar las propuestas IA.' });
      }
    });
  }

  approve(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.approve(item.id, item.proposal_version, 'Aprobada desde CRM').pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set({ error: false, text: `Propuesta #${item.id} aprobada.` });
        this.reload();
      },
      error: (err: HttpErrorResponse) => this.handleMutationError(err)
    });
  }

  reject(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.reject(item.id, item.proposal_version, 'Rechazada desde CRM').pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set({ error: false, text: `Propuesta #${item.id} rechazada.` });
        this.reload();
      },
      error: (err: HttpErrorResponse) => this.handleMutationError(err)
    });
  }

  execute(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.execute(item.id, item.proposal_version).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set({ error: false, text: `Propuesta #${item.id} ejecutada.` });
        this.reload();
      },
      error: (err: HttpErrorResponse) => this.handleMutationError(err)
    });
  }

  private handleMutationError(err: HttpErrorResponse): void {
    this.busy.set(false);
    this.notice.set({
      error: true,
      text: err.status === 409 ? 'La propuesta cambió o expiró. Recargando…' : 'No pudimos procesar la propuesta.'
    });
    if (err.status === 409) this.reload();
  }
}
