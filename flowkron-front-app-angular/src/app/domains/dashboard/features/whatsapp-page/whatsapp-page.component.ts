import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, catchError, exhaustMap, finalize, map, timer } from 'rxjs';
import { API_BASE_URL } from '@core/config/api.config';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ApiResponse } from '@shared/types/api.types';

type ConnectionStatus = 'disconnected' | 'connecting' | 'qr_pending' | 'connected' | 'pairing_required';

interface WhatsAppSession {
  status: ConnectionStatus;
  qr?: string;
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
  imports: [RouterLink],
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
  readonly statusLabel = computed(() => {
    const state = this.session();
    return state ? statusLabels[state.status] : this.error() ? 'Estado no disponible' : 'Consultando conexión…';
  });

  ngOnInit(): void {
    timer(0, 2500).pipe(
      exhaustMap(() => this.busy() || this.forbidden() ? EMPTY : this.request('GET').pipe(
        catchError((error: unknown) => {
          if (!this.busy()) this.reportError(error);
          return EMPTY;
        })
      )),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe((session) => {
      if (this.busy()) return;
      this.session.set(session);
      this.error.set('');
    });
  }

  update(method: 'POST' | 'DELETE'): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.request(method).pipe(
      finalize(() => this.busy.set(false)),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: (session) => {
        this.session.set(session);
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
    if (error instanceof HttpErrorResponse && error.status === 403) {
      this.forbidden.set(true);
      this.error.set('Tu rol no permite vincular WhatsApp. Contacta a quien administra tu empresa.');
      return;
    }
    this.session.set(null);
    this.error.set('No pudimos consultar el conector. Reintenta en unos segundos.');
  }
}
