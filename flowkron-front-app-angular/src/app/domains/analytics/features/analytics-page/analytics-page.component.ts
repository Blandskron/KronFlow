import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  LucideCalendar,
  LucideCheckCircle2,
  LucideClock,
  LucideDollarSign,
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
    LucideCalendar,
    LucideCheckCircle2,
    LucideClock,
    LucideDollarSign,
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

  metrics: { label: string; value: string; change: string; trend: string; icon: string }[] = [];

  channelStats: { channel: string; conversations: number; conversion: string }[] = [];

  recentActivity: { time: string; event: string; user: string; type: string }[] = [];

  constructor() {
    effect(() => {
      if (!this.auth.subscription()?.requires_paid_plan && this.planRequired()) {
        setTimeout(() => this.planRequired.set(false));
      }

      if (!this.requiresPlan() && !this.hasLoaded() && !this.isLoading()) {
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

  private loadAnalytics(): void {
    if (this.isLoading() || this.hasLoaded()) {
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    this.operational.analyticsSummary().subscribe({
      next: (summary) => {
        this.metrics = [
          { label: 'Leads Totales', value: String(summary.total_leads), change: 'Real', trend: 'up', icon: 'users' },
          { label: 'Leads Calientes', value: String(summary.hot_leads), change: 'Real', trend: 'up', icon: 'check-circle-2' },
          { label: 'Requieren Ejecutivo', value: String(summary.requires_human), change: 'Real', trend: 'down', icon: 'x-circle' },
          { label: 'Conversaciones Abiertas', value: String(summary.open_conversations), change: 'Real', trend: 'up', icon: 'message-square' },
          { label: 'Mensajes Hoy', value: String(summary.messages_today), change: 'Real', trend: 'up', icon: 'clock' },
          { label: 'Mensajes 7 Dias', value: String(summary.messages_last_7_days), change: 'Real', trend: 'up', icon: 'message-square' }
        ];
        this.channelStats = [
          { channel: 'Leads Frios', conversations: summary.cold_leads, conversion: this.percent(summary.cold_leads, summary.total_leads) },
          { channel: 'Leads Tibios', conversations: summary.warm_leads, conversion: this.percent(summary.warm_leads, summary.total_leads) },
          { channel: 'Leads Calientes', conversations: summary.hot_leads, conversion: this.percent(summary.hot_leads, summary.total_leads) }
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
    this.channelStats = [];
    this.recentActivity = [];
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
