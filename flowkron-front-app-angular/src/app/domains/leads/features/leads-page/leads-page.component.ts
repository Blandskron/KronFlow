import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { Lead, leadStages } from '@domains/leads/domain/lead.model';
import { PaginatedResponse } from '@shared/types/api.types';
import { BehaviorSubject, catchError, finalize, map, of, startWith, switchMap } from 'rxjs';

type LeadGroup = 'open' | 'closed';
type QueueState = { status: 'loading' | 'error' } | { status: 'ready'; page: PaginatedResponse<Lead> };

@Component({
  selector: 'flowkron-leads-page',
  standalone: true,
  imports: [DatePipe, RouterLink],
  templateUrl: './leads-page.component.html',
  styles: `
    .leads { padding: clamp(18px, 3vw, 32px); }
    .filters, .pagination, .stage { display: flex; flex-wrap: wrap; align-items: end; gap: 8px; }
    .filters label { display: grid; gap: 4px; }
    .filters { margin-block: 16px; }
    .item { margin-block: 10px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
    .item h2 { margin: 0; font-size: 1rem; overflow-wrap: anywhere; }
    .item p { margin: 4px 0 0; }
    .stage .field { width: auto; }
    .pagination { align-items: center; margin-block: 12px; }
  `
})
export class LeadsPageComponent {
  private readonly leads = inject(LeadsApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly contactId = Number(inject(ActivatedRoute).snapshot.queryParamMap.get('contact_id'));
  readonly contactFilter = Number.isSafeInteger(this.contactId) && this.contactId > 0 ? this.contactId : undefined;
  private readonly requests = new BehaviorSubject({ query: '', group: undefined as LeadGroup | undefined, offset: 0 });
  readonly auth = inject(AuthService);
  readonly stages = leadStages;
  readonly saving = signal<number | null>(null);
  readonly notice = signal<{ error: boolean; message: string } | null>(null);

  readonly queue = toSignal(this.requests.pipe(
    switchMap(({ query, group, offset }) => this.leads.listLeads({
      contact_id: this.contactFilter, q: query, status_group: group, limit: 25, offset
    }).pipe(
      map((page): QueueState => ({ status: 'ready', page })),
      catchError(() => of<QueueState>({ status: 'error' })),
      startWith<QueueState>({ status: 'loading' })
    ))
  ), { requireSync: true });

  search(query: string, group: string): void {
    this.notice.set(null);
    this.requests.next({ query: query.trim(), group: group === 'open' || group === 'closed' ? group : undefined, offset: 0 });
  }

  page(offset: number): void {
    this.requests.next({ ...this.requests.value, offset: Math.max(0, offset) });
  }

  refresh(): void {
    this.requests.next(this.requests.value);
  }

  stageLabel(id: string): string {
    return this.stages.find((stage) => stage.id === id)?.label ?? id;
  }

  updateStage(lead: Lead, stage: string): void {
    if (this.saving() !== null || stage === lead.lifecycle_status) return;
    this.saving.set(lead.id);
    this.notice.set(null);
    this.leads.updateStage(lead, stage).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(null))
    ).subscribe({
      next: () => {
        this.notice.set({ error: false, message: 'Etapa guardada.' });
        this.refresh();
      },
      error: (error: HttpErrorResponse) => {
        this.notice.set({ error: true, message: error.status === 409
          ? 'El lead cambió en otra sesión. Actualiza la lista antes de volver a guardar.'
          : 'No pudimos guardar la etapa.' });
      }
    });
  }
}
