import { DatePipe, Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { Lead, LeadActivity, leadStages, leadTemperatures } from '@domains/leads/domain/lead.model';
import { Subject, catchError, combineLatest, distinctUntilChanged, filter, finalize, map, of, shareReplay, startWith, switchMap, takeUntil, tap } from 'rxjs';

type DetailState = { status: 'loading' } | { status: 'error'; message: string; retryable: boolean } | { status: 'ready'; lead: Lead };

@Component({
  selector: 'flowkron-lead-detail-page',
  standalone: true,
  imports: [DatePipe, RouterLink],
  templateUrl: './lead-detail-page.component.html',
  styles: `
    .lead-detail { padding: clamp(18px, 3vw, 32px); }
    .lead-detail h1, .lead-detail dd { overflow-wrap: anywhere; }
    .lead-detail .card { margin-block: 16px; max-width: 48rem; }
    dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px; margin: 0; }
    dt { font-weight: 700; }
    dd { margin: 4px 0 0; }
    form { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }
    label { display: grid; gap: 4px; }
    .history li { margin-block: 8px; }
  `
})
export class LeadDetailPageComponent {
  private readonly api = inject(LeadsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly location = inject(Location);
  private readonly leadId$ = this.route.paramMap.pipe(map((params) => params.get('id') ?? ''), distinctUntilChanged());
  private readonly reload = new Subject<void>();
  private readonly reloadActivity = new Subject<void>();

  readonly auth = inject(AuthService);
  readonly stages = leadStages;
  readonly temperatures = leadTemperatures;
  readonly backState = { leadSearch: (this.location.getState() as { leadSearch?: unknown } | null)?.leadSearch };
  readonly saving = signal(false);
  readonly notice = signal<{ error: boolean; message: string } | null>(null);

  private readonly detail$ = combineLatest([
    this.leadId$.pipe(tap(() => this.notice.set(null))), this.reload.pipe(startWith(undefined))
  ]).pipe(
    switchMap(([id]) => this.api.get(id).pipe(
      map((lead): DetailState => ({ status: 'ready', lead })),
      catchError((error: HttpErrorResponse) => {
        if (error.status === 403) return of<DetailState>({ status: 'error', retryable: false, message: 'No tienes permiso para consultar este lead.' });
        if (error.status === 404 || error.status === 422) {
          return of<DetailState>({ status: 'error', retryable: false, message: 'No encontramos este lead en la empresa actual.' });
        }
        return of<DetailState>({ status: 'error', retryable: true, message: 'No pudimos consultar el lead.' });
      }),
      startWith<DetailState>({ status: 'loading' })
    )),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly detail = toSignal(this.detail$, { requireSync: true });
  readonly history = toSignal(combineLatest([this.detail$, this.reloadActivity.pipe(startWith(undefined))]).pipe(
    switchMap(([state]) => state.status !== 'ready' || !this.auth.hasPermission('audit.read') ? of(undefined) : this.api.activity(state.lead.id).pipe(
      catchError(() => of(null)), startWith(undefined)
    ))
  ));

  retry(): void { this.reload.next(); }
  retryHistory(): void { this.reloadActivity.next(); }

  stageLabel(id: string | null): string { return this.stages.find((stage) => stage.id === id)?.label ?? id ?? 'Sin etapa'; }
  temperatureLabel(id: string | null): string {
    return this.temperatures.find((temperature) => temperature.id === id)?.label ?? id ?? 'Sin temperatura';
  }

  activityLabel(event: LeadActivity): string {
    if (event.kind === 'created') return 'Seguimiento iniciado';
    if (event.kind === 'stage') return `Etapa: ${this.stageLabel(event.previous)} → ${this.stageLabel(event.value)}`;
    return `Temperatura: ${this.temperatureLabel(event.previous)} → ${this.temperatureLabel(event.value)}`;
  }

  save(lead: Lead, stage: string, temperature: string): void {
    if (this.saving()) return;
    const changes = {
      lifecycle_status: stage !== lead.lifecycle_status ? stage : undefined,
      temperature: temperature !== lead.temperature ? temperature : undefined
    };
    if (!changes.lifecycle_status && !changes.temperature) return;

    const routeId = this.route.snapshot.paramMap.get('id') ?? '';
    this.saving.set(true);
    this.notice.set(null);
    this.api.update(lead, changes).pipe(
      takeUntil(this.leadId$.pipe(filter((id) => id !== routeId))),
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))
    ).subscribe({
      next: () => { this.notice.set({ error: false, message: 'Cambios guardados.' }); this.retry(); },
      error: (error: HttpErrorResponse) => {
        const conflict = error.status === 409;
        this.notice.set({ error: true, message: conflict
          ? 'El lead cambió en otra sesión. Revisa los valores actuales antes de guardar.'
          : 'No pudimos guardar los cambios.' });
        if (conflict || error.status === 404) this.retry();
      }
    });
  }
}
