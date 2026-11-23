import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  OpportunitiesApiService,
  OpportunityItem,
  PipelineStage
} from '@domains/leads/data-access/opportunities-api.service';

@Component({
  selector: 'flowkron-opportunities-page',
  standalone: true,
  imports: [DatePipe],
  template: `
    <section class="page-section">
      <header class="heading">
        <div>
          <h1>Pipeline de oportunidades</h1>
          <p class="muted">Gestiona etapas comerciales, importes y cierres ganados o perdidos.</p>
        </div>
        <button class="btn btn-secondary" type="button" [disabled]="loading()" (click)="reload()">
          {{ loading() ? 'Actualizando…' : 'Actualizar' }}
        </button>
      </header>

      @if (notice(); as msg) {
        <p class="muted" [attr.role]="msg.error ? 'alert' : 'status'" style="margin-block:12px">{{ msg.text }}</p>
      }

      @if (canManage()) {
        <form class="card glass-surface" style="display:flex;flex-wrap:wrap;gap:10px;align-items:end;padding:16px;margin-bottom:16px" (submit)="$event.preventDefault(); createOpportunity()">
          <label style="display:grid;gap:4px">
            <small class="muted">Título</small>
            <input #titleInput type="text" required maxlength="160" placeholder="Ej. Flota anual" [value]="newTitle()" (input)="newTitle.set(titleInput.value)">
          </label>
          <label style="display:grid;gap:4px">
            <small class="muted">ID Contacto</small>
            <input #contactInput type="number" min="1" required placeholder="1" [value]="newContactId()" (input)="newContactId.set(contactInput.value)">
          </label>
          <label style="display:grid;gap:4px">
            <small class="muted">Importe</small>
            <input #amountInput type="number" min="0" step="0.01" placeholder="1500.00" [value]="newAmount()" (input)="newAmount.set(amountInput.value)">
          </label>
          <label style="display:grid;gap:4px">
            <small class="muted">Moneda</small>
            <input #currInput type="text" maxlength="3" style="width:76px" [value]="newCurrency()" (input)="newCurrency.set(currInput.value)">
          </label>
          <button class="btn btn-primary" type="submit" [disabled]="saving() || !newTitle().trim() || !newContactId().trim()">
            Crear oportunidad
          </button>
        </form>
      }

      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px" role="group" aria-label="Filtrar por resultado">
        @for (opt of outcomeFilters; track opt.id) {
          <button class="btn btn-secondary" type="button" [attr.aria-pressed]="outcomeFilter() === opt.id" (click)="setOutcomeFilter(opt.id)">
            {{ opt.label }}
          </button>
        }
      </div>

      @if (loading() && !items().length) {
        <p class="muted" role="status">Cargando oportunidades…</p>
      } @else if (!items().length) {
        <p class="muted" role="status">No hay oportunidades registradas para este filtro.</p>
      } @else {
        <div style="display:grid;gap:12px">
          @for (opp of items(); track opp.id) {
            <article class="card glass-surface" style="padding:16px;display:grid;gap:8px">
              <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:center">
                <strong>#{{ opp.id }} · {{ opp.title }}</strong>
                <span class="badge badge-info">{{ opp.stage_name }} ({{ outcomeLabels[opp.outcome] }})</span>
              </div>
              <small class="muted">
                Contacto #{{ opp.contact_id }}
                @if (opp.lead_id) { · Lead #{{ opp.lead_id }} }
                @if (opp.amount) { · {{ opp.amount }} {{ opp.currency }} }
                · v{{ opp.version }} · Actualizada {{ opp.updated_at | date:'short' }}
              </small>
              @if (opp.close_reason) {
                <small class="muted">Motivo de cierre: {{ opp.close_reason }}</small>
              }
              @if (canManage() && opp.outcome === 'open') {
                <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px">
                  <select #stageSelect aria-label="Cambiar etapa" [value]="opp.stage_id" (change)="moveStage(opp, +stageSelect.value)">
                    @for (stage of stages(); track stage.id) {
                      @if (stage.stage_kind === 'open') {
                        <option [value]="stage.id" [selected]="stage.id === opp.stage_id">{{ stage.name }}</option>
                      }
                    }
                  </select>
                  <button class="btn btn-primary" type="button" [disabled]="saving()" (click)="closeWon(opp)">Marcar ganada</button>
                  <button class="btn btn-secondary" type="button" [disabled]="saving()" (click)="closeLost(opp)">Marcar perdida</button>
                </div>
              }
            </article>
          }
        </div>
      }
    </section>
  `
})
export class OpportunitiesPageComponent implements OnInit {
  private readonly api = inject(OpportunitiesApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly stages = signal<PipelineStage[]>([]);
  readonly items = signal<OpportunityItem[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly outcomeFilter = signal('');
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly newTitle = signal('');
  readonly newContactId = signal('');
  readonly newAmount = signal('');
  readonly newCurrency = signal('USD');

  readonly outcomeFilters = [
    { id: '', label: 'Todas' },
    { id: 'open', label: 'Abiertas' },
    { id: 'won', label: 'Ganadas' },
    { id: 'lost', label: 'Perdidas' }
  ];
  readonly outcomeLabels: Record<OpportunityItem['outcome'], string> = {
    open: 'Abierta',
    won: 'Ganada',
    lost: 'Perdida'
  };

  ngOnInit(): void {
    this.api.listStages().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (stages) => this.stages.set(stages),
      error: () => undefined
    });
    this.reload();
  }

  setOutcomeFilter(outcome: string): void {
    this.outcomeFilter.set(outcome);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    const outcome = this.outcomeFilter() || undefined;
    this.api.list({ outcome, limit: 50 }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (page) => {
        this.items.set(page.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.notice.set({ error: true, text: 'No pudimos cargar las oportunidades.' });
      }
    });
  }

  createOpportunity(): void {
    const contactId = Number(this.newContactId());
    if (!this.newTitle().trim() || !Number.isSafeInteger(contactId) || contactId < 1 || this.saving()) return;
    this.saving.set(true);
    this.notice.set(null);
    const amountVal = this.newAmount().trim() ? Number(this.newAmount()) : undefined;
    this.api.create({
      title: this.newTitle().trim(),
      contact_id: contactId,
      amount: Number.isFinite(amountVal) ? amountVal : undefined,
      currency: this.newCurrency().trim().toUpperCase() || 'USD'
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.newTitle.set('');
        this.newContactId.set('');
        this.newAmount.set('');
        this.saving.set(false);
        this.notice.set({ error: false, text: 'Oportunidad creada.' });
        this.reload();
      },
      error: () => {
        this.saving.set(false);
        this.notice.set({ error: true, text: 'No pudimos crear la oportunidad. Verifica el ID de contacto.' });
      }
    });
  }

  moveStage(opp: OpportunityItem, stageId: number): void {
    if (stageId === opp.stage_id || this.saving()) return;
    this.saving.set(true);
    this.api.update(opp.id, { expected_version: opp.version, stage_id: stageId }).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.saving.set(false);
        this.notice.set({ error: false, text: `Oportunidad #${opp.id} movida de etapa.` });
        this.reload();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        this.notice.set({ error: true, text: err.status === 409 ? 'La oportunidad cambió en otra sesión. Recargando…' : 'No pudimos actualizar la etapa.' });
        if (err.status === 409) this.reload();
      }
    });
  }

  closeWon(opp: OpportunityItem): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.api.update(opp.id, { expected_version: opp.version, outcome: 'won', close_reason: 'Cerrada desde CRM' }).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.saving.set(false);
        this.notice.set({ error: false, text: `Oportunidad #${opp.id} cerrada como ganada.` });
        this.reload();
      },
      error: () => {
        this.saving.set(false);
        this.notice.set({ error: true, text: 'No pudimos cerrar la oportunidad.' });
      }
    });
  }

  closeLost(opp: OpportunityItem): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.api.update(opp.id, { expected_version: opp.version, outcome: 'lost', close_reason: 'Descartada desde CRM' }).pipe(
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: () => {
        this.saving.set(false);
        this.notice.set({ error: false, text: `Oportunidad #${opp.id} cerrada como perdida.` });
        this.reload();
      },
      error: () => {
        this.saving.set(false);
        this.notice.set({ error: true, text: 'No pudimos cerrar la oportunidad.' });
      }
    });
  }
}
