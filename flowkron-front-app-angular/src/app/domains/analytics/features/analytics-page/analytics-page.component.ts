import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  LucideCheckCircle2,
  LucideClock,
  LucideMessageSquare,
  LucideUsers,
  LucideXCircle
} from '@lucide/angular';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AnalyticsApiService } from '@domains/analytics/data-access/analytics-api.service';

@Component({
  selector: 'flowkron-analytics-page',
  standalone: true,
  imports: [
    LucideCheckCircle2,
    LucideClock,
    LucideMessageSquare,
    LucideUsers,
    LucideXCircle,
    RouterLink
  ],
  templateUrl: './analytics-page.component.html',
  styleUrl: './analytics-page.component.css'
})
export class AnalyticsPageComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly operational = inject(AnalyticsApiService);
  readonly planRequired = signal(false);
  readonly hasLoaded = signal(false);
  readonly isLoading = signal(false);
  readonly loadError = signal('');

  readonly requiresPlan = computed(() => Boolean(this.auth.subscription()?.requires_paid_plan || this.planRequired()));

  metrics: { label: string; value: string; icon: string }[] = [];

  leadStats: { label: string; count: number; share: string }[] = [];

  constructor() {
    effect(() => {
      if (!this.requiresPlan() && !this.hasLoaded() && !this.isLoading() && !this.loadError()) {
        setTimeout(() => this.loadAnalytics());
      }
    });
  }

  ngOnInit(): void {
    if (this.requiresPlan()) {
      this.setEmptyAnalytics();
      return;
    }

    this.loadAnalytics();
  }

  loadAnalytics(): void {
    if (this.isLoading() || this.hasLoaded()) {
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    this.operational.analyticsSummary().subscribe({
      next: (summary) => {
        this.metrics = [
          { label: 'Total de oportunidades', value: String(summary.total_leads), icon: 'users' },
          { label: 'Oportunidades calientes', value: String(summary.hot_leads), icon: 'check-circle-2' },
          { label: 'Requieren atención', value: String(summary.requires_human), icon: 'x-circle' },
          { label: 'Conversaciones abiertas', value: String(summary.open_conversations), icon: 'message-square' },
          { label: 'Mensajes de hoy', value: String(summary.messages_today), icon: 'clock' },
          { label: 'Mensajes en los últimos 7 días', value: String(summary.messages_last_7_days), icon: 'message-square' }
        ];
        this.leadStats = [
          { label: 'Frías', count: summary.cold_leads, share: this.percent(summary.cold_leads, summary.total_leads) },
          { label: 'Tibias', count: summary.warm_leads, share: this.percent(summary.warm_leads, summary.total_leads) },
          { label: 'Calientes', count: summary.hot_leads, share: this.percent(summary.hot_leads, summary.total_leads) }
        ];
        this.hasLoaded.set(true);
        this.isLoading.set(false);
      },
      error: (error) => {
        if (this.isPlanAccessError(error)) {
          this.planRequired.set(true);
          this.setEmptyAnalytics();
          this.hasLoaded.set(true);
        } else {
          this.loadError.set(this.operationalErrorMessage(error));
        }
        this.isLoading.set(false);
      }
    });
  }

  private percent(value: number, total: number): string {
    if (!total) {
      return '0%';
    }
    return `${Math.round((value / total) * 100)}%`;
  }

  private setEmptyAnalytics(): void {
    this.metrics = [];
    this.leadStats = [];
  }

  private isPlanAccessError(error: unknown): boolean {
    return error instanceof HttpErrorResponse && error.status === 402;
  }

  private operationalErrorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return 'El servicio operacional no respondio correctamente.';
    }
    if (error.status === 401) {
      return 'Tu sesion expiro o no pudo validarse con operational. Vuelve a iniciar sesion.';
    }
    if (error.status === 403) {
      return 'El tenant no tiene acceso operacional activo o esta suspendido.';
    }
    if (error.status === 404) {
      return 'El entorno operacional del tenant aun no esta provisionado.';
    }
    return 'El servicio operacional no respondio correctamente.';
  }
}
