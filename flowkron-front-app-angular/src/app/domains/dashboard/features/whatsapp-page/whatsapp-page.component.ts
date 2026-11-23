import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError, exhaustMap, finalize, map, timer } from 'rxjs';
import { API_BASE_URL } from '@core/config/api.config';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ApiResponse } from '@shared/types/api.types';

type ConnectionStatus = 'disconnected' | 'connecting' | 'qr_pending' | 'connected' | 'pairing_required';
type ConnectionAction = 'connect' | 'scan' | 'wait' | 'retry' | 'relink' | 'none';

const causeLabels = {
  signed_out: 'Se cerró la sesión en WhatsApp.',
  invalid_session: 'Las credenciales del vínculo ya no son válidas.',
  replaced_session: 'WhatsApp reemplazó esta sesión por otra conexión.',
  provider_denied: 'WhatsApp rechazó la conexión.',
  device_mismatch: 'WhatsApp requiere vincular nuevamente el dispositivo.',
  temporary: 'La conexión con WhatsApp se interrumpió.',
  startup_failed: 'El conector no pudo iniciar la sesión.',
  workspace_unavailable: 'El espacio de trabajo todavía no está disponible para WhatsApp.',
  manual: 'La cuenta se desconectó desde Flowkron.'
};

interface WhatsAppSession {
  status: ConnectionStatus;
  qr?: string;
  diagnostics?: {
    status_changed_at: string;
    last_connected_at?: string;
    disconnect_cause?: keyof typeof causeLabels;
    recent_transitions?: { status: ConnectionStatus; changed_at: string }[];
    retry_attempts: number;
    retry_limit: number;
    next_retry_at?: string;
    retry_exhausted: boolean;
    next_action: ConnectionAction;
    qr_expires_at?: string;
  };
}

const statusLabels: Record<ConnectionStatus, string> = {
  disconnected: 'Sin conectar',
  connecting: 'Preparando la conexión…',
  qr_pending: 'Esperando el escaneo',
  connected: 'Conectado',
  pairing_required: 'Hay que volver a vincular la cuenta'
};

@Component({
  selector: 'flowkron-whatsapp-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink],
  templateUrl: './whatsapp-page.component.html',
  styleUrl: './whatsapp-page.component.css'
})
export class WhatsAppPageComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  readonly session = signal<WhatsAppSession | null>(null);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly confirmDisconnect = signal(false);
  private readonly forbidden = signal(false);
  private mutationVersion = 0;
  private qrExpiryTimer?: ReturnType<typeof setTimeout>;
  readonly statusLabels = statusLabels;
  readonly causeLabel = computed(() => {
    const cause = this.session()?.diagnostics?.disconnect_cause;
    return cause ? causeLabels[cause] : '';
  });
  readonly nextAction = computed<ConnectionAction>(() => {
    const state = this.session();
    if (!state) return 'none';
    if (state.status === 'qr_pending') return state.qr ? 'scan' : 'wait';
    return state.diagnostics?.next_action ?? (state.status === 'disconnected' ? 'connect' : 'none');
  });
  readonly statusLabel = computed(() => {
    const state = this.session();
    if (!state) return this.error() ? 'Estado no disponible' : 'Consultando conexión…';
    if (state.diagnostics?.retry_exhausted) return 'Se agotaron los intentos de reconexión';
    if (state.diagnostics?.next_retry_at) return 'Reconexión programada';
    if (state.status === 'qr_pending' && !state.qr) return 'Esperando un código nuevo';
    return statusLabels[state.status];
  });

  ngOnInit(): void {
    this.destroyRef.onDestroy(() => clearTimeout(this.qrExpiryTimer));
    timer(0, 2500).pipe(
      exhaustMap(() => {
        if (this.busy() || this.forbidden()) return EMPTY;
        const version = this.mutationVersion;
        return this.request('GET').pipe(
          map((session) => ({ session, version })),
          catchError((error: unknown) => {
            if (version === this.mutationVersion) this.reportError(error);
            return EMPTY;
          })
        );
      }),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(({ session, version }) => {
      if (version !== this.mutationVersion) return;
      this.applySession(session);
      this.error.set('');
    });
  }

  update(method: 'POST' | 'DELETE'): void {
    if (this.busy()) return;
    this.mutationVersion++;
    this.busy.set(true);
    this.error.set('');
    this.request(method).pipe(
      finalize(() => this.busy.set(false)),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (session) => {
        this.applySession(session);
        this.confirmDisconnect.set(false);
      },
      error: (error: unknown) => this.reportError(error)
    });
  }

  private request(method: 'GET' | 'POST' | 'DELETE') {
    const url = `${API_BASE_URL}/tenants/${this.auth.getTenantId()}/whatsapp/`;
    return this.http.request<ApiResponse<WhatsAppSession>>(method, url).pipe(map((response) => response.data));
  }

  private reportError(error: unknown): void {
    this.applySession(null);
    if (error instanceof HttpErrorResponse && error.status === 403) {
      this.forbidden.set(true);
      this.error.set('Tu rol no permite vincular WhatsApp. Contacta a quien administra tu empresa.');
      return;
    }
    this.error.set('No pudimos consultar el conector. Reintenta en unos segundos.');
  }

  private applySession(session: WhatsAppSession | null): void {
    clearTimeout(this.qrExpiryTimer);
    const remaining = Date.parse(session?.diagnostics?.qr_expires_at ?? '') - Date.now();
    if (!session?.qr || session.status !== 'qr_pending' || !(remaining > 0)) {
      this.session.set(session ? { ...session, qr: undefined } : null);
      return;
    }
    this.session.set(session);
    this.qrExpiryTimer = setTimeout(() => {
      if (this.session() === session) this.session.set({ ...session, qr: undefined });
    }, remaining);
  }
}
