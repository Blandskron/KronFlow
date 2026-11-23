import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { Lead, leadStages, leadTemperatures } from '@domains/leads/domain/lead.model';
import { PaginatedResponse } from '@shared/types/api.types';
import { Subject, catchError, combineLatest, distinctUntilChanged, filter, finalize, map, of, shareReplay, startWith, switchMap, tap } from 'rxjs';

type LeadGroup = 'open' | 'closed';
type LeadFilters = { contactId?: number; query: string; group?: LeadGroup; temperature?: string; offset: number };
type QueueState =
  | { status: 'loading' }
  | { status: 'error'; forbidden: boolean }
  | { status: 'ready'; page: PaginatedResponse<Lead> };

const pageSize = 25;

function leadGroup(value: string | null): LeadGroup | undefined {
  return value === 'open' || value === 'closed' ? value : undefined;
}

function leadTemperature(value: string | null): string | undefined {
  return leadTemperatures.find((option) => option.id === value)?.id;
}

function sameFilters(a: LeadFilters, b: LeadFilters): boolean {
  return a.contactId === b.contactId && a.query === b.query && a.group === b.group
    && a.temperature === b.temperature && a.offset === b.offset;
}

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
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly location = inject(Location);
  private readonly reload = new Subject<void>();

  readonly auth = inject(AuthService);
  readonly stages = leadStages;
  readonly temperatures = leadTemperatures;
  readonly saving = signal<number | null>(null);
  readonly notice = signal<{ error: boolean; message: string } | null>(null);

  private readonly filters$ = this.router.events.pipe(
    filter((event) => event instanceof NavigationEnd),
    startWith(null),
    map((): LeadFilters => {
      const params = this.route.snapshot.queryParamMap;
      const contactId = Number(params.get('contact_id'));
      const offset = Number(params.get('offset'));
      const state = this.location.getState() as { leadSearch?: unknown } | null;
      return {
        contactId: Number.isSafeInteger(contactId) && contactId > 0 ? contactId : undefined,
        query: typeof state?.leadSearch === 'string' ? state.leadSearch.slice(0, 120) : '',
        group: leadGroup(params.get('status_group')),
        temperature: leadTemperature(params.get('temperature')),
        offset: Number.isSafeInteger(offset) && offset > 0 ? offset : 0
      };
    }),
    distinctUntilChanged(sameFilters),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly filters = toSignal(this.filters$, { requireSync: true });

  readonly queue = toSignal(combineLatest([this.filters$, this.reload.pipe(startWith(undefined))]).pipe(
    switchMap(([filters]) => this.leads.listLeads({
      contact_id: filters.contactId, q: filters.query, status_group: filters.group, temperature: filters.temperature,
      limit: pageSize, offset: filters.offset
    }).pipe(
      tap((page) => {
        if (!page.items.length && page.offset > 0 && page.offset >= page.total && page.limit > 0) {
          const lastOffset = Math.floor(Math.max(0, page.total - 1) / page.limit) * page.limit;
          if (lastOffset !== filters.offset) this.navigate({ ...filters, offset: lastOffset }, true);
        }
      }),
      map((page): QueueState => ({ status: 'ready', page })),
      catchError((error: HttpErrorResponse) => of<QueueState>({ status: 'error', forbidden: error.status === 403 })),
      startWith<QueueState>({ status: 'loading' })
    ))
  ), { requireSync: true });

  search(query: string, group: string, temperature: string): void {
    this.notice.set(null);
    this.navigate({ ...this.filters(), query: query.trim(), group: leadGroup(group), temperature: leadTemperature(temperature), offset: 0 });
  }

  clearContact(): void {
    this.notice.set(null);
    this.navigate({ ...this.filters(), contactId: undefined, offset: 0 });
  }

  page(offset: number): void {
    this.notice.set(null);
    this.navigate({ ...this.filters(), offset: Math.max(0, offset) });
  }

  refresh(): void {
    this.reload.next();
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
        if (error.status === 409 || error.status === 404) {
          this.notice.set({ error: true, message: error.status === 409
            ? 'El lead cambió en otra sesión. Revisa la etapa actual antes de volver a guardar.'
            : 'El lead ya no está disponible. Actualizamos la lista.' });
          this.refresh();
          return;
        }
        this.notice.set({ error: true, message: 'No pudimos guardar la etapa.' });
      }
    });
  }

  private navigate(filters: LeadFilters, replaceUrl = false): void {
    const current = this.filters();
    if (sameFilters(current, filters)) {
      this.refresh();
      return;
    }
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        contact_id: filters.contactId ?? null, status_group: filters.group ?? null,
        temperature: filters.temperature ?? null, offset: filters.offset || null
      },
      state: { leadSearch: filters.query },
      replaceUrl,
      onSameUrlNavigation: 'reload'
    });
  }
}
