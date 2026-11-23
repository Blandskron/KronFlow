import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { PrivacyCase, PrivacyCasesApiService, PrivacyState } from '@domains/settings/data-access/privacy-cases-api.service';
import { PaginatedResponse } from '@shared/types/api.types';
import { BehaviorSubject, catchError, finalize, map, of, startWith, switchMap } from 'rxjs';

type CaseList = { status: 'loading' } | { status: 'error'; forbidden: boolean }
  | { status: 'ready'; page: PaginatedResponse<PrivacyCase> };

@Component({
  selector: 'flowkron-privacy-cases-page',
  standalone: true,
  imports: [DatePipe, RouterLink],
  templateUrl: './privacy-cases-page.component.html',
  styles: `
    .page-section { padding: clamp(18px, 3vw, 32px); }
    .filters, .pagination { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-block: 16px; }
    .filters label { display: grid; gap: 4px; }
    article { margin-block: 12px; }
    article h2 { margin: 0 0 8px; font-size: 1.1rem; }
    article p { margin: 4px 0; }
    .case-action { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
  `
})
export class PrivacyCasesPageComponent {
  private readonly api = inject(PrivacyCasesApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly query = new BehaviorSubject({ state: 'pendiente', offset: 0 });
  readonly auth = inject(AuthService);
  readonly saving = signal(false);
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly labels: Record<PrivacyState, string> = { pendiente: 'Pendiente', en_proceso: 'En revisión', completada: 'Completada' };
  readonly kinds: Record<string, string> = {
    acceso: 'Acceso', rectificacion: 'Rectificación', eliminacion: 'Eliminación', oposicion: 'Oposición', portabilidad: 'Portabilidad'
  };
  readonly list = toSignal(this.query.pipe(
    switchMap(({ state, offset }) => this.auth.hasPermission('audit.read') ? this.api.list(state, offset).pipe(
      map((page): CaseList => ({ status: 'ready', page })),
      catchError((error: HttpErrorResponse) => of<CaseList>({ status: 'error', forbidden: error.status === 403 })),
      startWith<CaseList>({ status: 'loading' })
    ) : of<CaseList>({ status: 'error', forbidden: true }))
  ), { requireSync: true });

  filter(state: string): void {
    this.notice.set(null);
    this.query.next({ state, offset: 0 });
  }

  page(offset: number): void {
    this.query.next({ ...this.query.value, offset: Math.max(0, offset) });
  }

  retry(): void { this.query.next(this.query.value); }

  advance(entry: PrivacyCase, confirmed = false): void {
    if (this.saving() || entry.state === 'completada' || (entry.state === 'en_proceso' && !confirmed)) return;
    this.saving.set(true);
    this.notice.set(null);
    const target = entry.state === 'pendiente' ? 'en_proceso' : 'completada';
    this.api.transition(entry, target, confirmed).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))
    ).subscribe({
      next: () => {
        this.notice.set({ error: false, text: `Solicitud #${entry.id} actualizada.` });
        this.retry();
      },
      error: (error: HttpErrorResponse) => {
        this.notice.set({ error: true, text: error.status === 409
          ? 'La solicitud cambió en otra sesión. Se actualizó la lista.' : 'No pudimos actualizar la solicitud.' });
        if (error.status === 409) this.retry();
      }
    });
  }
}
