import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuditEventFilters, AuditEventPage, AuditEventsApiService } from '@domains/settings/data-access/audit-events-api.service';
import { Subject, catchError, combineLatest, map, of, shareReplay, startWith, switchMap } from 'rxjs';

type AuditState = { status: 'loading' } | { status: 'error'; statusCode: number } | { status: 'ready'; page: AuditEventPage };

@Component({
  selector: 'kronflow-audit-events-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink],
  templateUrl: './audit-events-page.component.html',
  styles: `
    .page-section { padding: clamp(18px, 3vw, 32px); }
    form, .pagination { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; margin-block: 16px; }
    label { display: grid; gap: 4px; }
    .event { margin-block: 12px; overflow-wrap: anywhere; }
    .event h2 { margin: 0 0 8px; font-size: 1.1rem; }
    .event p { margin: 4px 0; }
    time { display: block; margin-block: 6px; }
  `
})
export class AuditEventsPageComponent {
  private readonly api = inject(AuditEventsApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly reload = new Subject<void>();
  readonly auth = inject(AuthService);
  readonly eventLabels: Record<string, string> = {
    'contact.created': 'Contacto creado', 'contact.renamed': 'Nombre de contacto editado',
    'contact.points.changed': 'Datos de contacto editados', 'lead.created': 'Lead creado',
    'lead.stage.changed': 'Cambio de etapa', 'lead.temperature.changed': 'Cambio de temperatura',
    'conversation.handoff.requested': 'Atención humana solicitada', 'privacy.case.state.changed': 'Cambio de estado de privacidad'
  };
  readonly eventTypes = Object.keys(this.eventLabels);
  private readonly filters$ = this.route.queryParamMap.pipe(
    map((params): AuditEventFilters => {
      const type = params.get('event_type') ?? '';
      const cursor = Number(params.get('before_id'));
      return {
        event_type: this.eventTypes.includes(type) ? type : '',
        correlation_id: (params.get('correlation_id') ?? '').slice(0, 36),
        before_id: Number.isInteger(cursor) && cursor > 0 && cursor <= 2147483647 ? cursor : undefined
      };
    }),
    shareReplay({ bufferSize: 1, refCount: true })
  );
  readonly filters = toSignal(this.filters$, { requireSync: true });
  readonly result = toSignal(combineLatest([this.filters$, this.reload.pipe(startWith(undefined))]).pipe(
    switchMap(([filters]) => this.auth.hasPermission('audit.read') ? this.api.list(filters).pipe(
      map((page): AuditState => ({ status: 'ready', page })),
      catchError((error: HttpErrorResponse) => of<AuditState>({ status: 'error', statusCode: error.status })),
      startWith<AuditState>({ status: 'loading' })
    ) : of<AuditState>({ status: 'error', statusCode: 403 }))
  ), { requireSync: true });

  search(eventType: string, correlationId: string): void {
    const current = this.filters();
    if (!current.before_id && current.event_type === eventType && current.correlation_id === correlationId.trim()) {
      this.retry();
      return;
    }
    void this.router.navigate([], {
      relativeTo: this.route, queryParams: { event_type: eventType || null, correlation_id: correlationId.trim() || null }
    });
  }

  retry(): void { this.reload.next(); }
}
