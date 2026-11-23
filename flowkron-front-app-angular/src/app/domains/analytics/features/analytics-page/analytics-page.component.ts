import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  LucideCheckCircle2,
  LucideClock,
  LucideMessageSquare,
  LucideUsers,
  LucideXCircle
} from '@lucide/angular';
import { AnalyticsApiService } from '@domains/analytics/data-access/analytics-api.service';
import { ActivityFilters, AnalyticsActivity } from '@domains/analytics/domain/analytics.model';
import { finalize } from 'rxjs';

function localDate(date: Date): string {
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()].map((part) => String(part).padStart(2, '0')).join('-');
}

function defaultDates(): ActivityFilters {
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 6);
  return { start_date: localDate(start), end_date: localDate(today), time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' };
}

@Component({
  selector: 'flowkron-analytics-page',
  standalone: true,
  imports: [
    DatePipe,
    LucideCheckCircle2,
    LucideClock,
    LucideMessageSquare,
    LucideUsers,
    LucideXCircle
  ],
  templateUrl: './analytics-page.component.html',
  styleUrl: './analytics-page.component.css'
})
export class AnalyticsPageComponent implements OnInit {
  private readonly operational = inject(AnalyticsApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly isLoading = signal(false);
  readonly loadError = signal('');
  readonly initialFilters = defaultDates();
  readonly activity = signal<AnalyticsActivity | null>(null);
  readonly activityLoading = signal(false);
  readonly activityError = signal('');

  metrics: { label: string; value: string; icon: string }[] = [];

  leadStats: { label: string; count: number; share: string | null }[] = [];

  ngOnInit(): void {
    this.loadAnalytics();
    this.loadActivity(this.initialFilters);
  }

  loadAnalytics(): void {
    if (this.isLoading()) {
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    this.operational.analyticsSummary().pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.isLoading.set(false))
    ).subscribe({
      next: (summary) => {
        this.metrics = [
          { label: 'Total de leads', value: String(summary.total_leads), icon: 'users' },
          { label: 'Leads calientes', value: String(summary.hot_leads), icon: 'check-circle-2' },
          { label: 'Requieren atención', value: String(summary.requires_human), icon: 'x-circle' },
          { label: 'Conversaciones abiertas', value: String(summary.open_conversations), icon: 'message-square' },
          { label: 'Mensajes de hoy (UTC)', value: String(summary.messages_today), icon: 'clock' },
          { label: 'Mensajes en los últimos 7 días', value: String(summary.messages_last_7_days), icon: 'message-square' }
        ];
        this.leadStats = [
          { label: 'Frías', count: summary.cold_leads, share: this.percent(summary.cold_leads, summary.total_leads) },
          { label: 'Tibias', count: summary.warm_leads, share: this.percent(summary.warm_leads, summary.total_leads) },
          { label: 'Calientes', count: summary.hot_leads, share: this.percent(summary.hot_leads, summary.total_leads) }
        ];
      },
      error: (error) => this.loadError.set(this.operationalErrorMessage(error))
    });
  }

  loadActivity(filters: ActivityFilters): void {
    if (this.activityLoading()) return;
    this.activity.set(null);
    this.activityError.set('');
    this.activityLoading.set(true);
    this.operational.activity({ ...filters, time_zone: filters.time_zone.trim() }).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.activityLoading.set(false))
    ).subscribe({
      next: (report) => this.activity.set(report),
      error: (error: HttpErrorResponse) => this.activityError.set(error.status === 422
        ? 'Revisa la zona horaria y el intervalo. Elige hasta 31 días, terminando como máximo hoy en esa zona.'
        : this.operationalErrorMessage(error))
    });
  }

  private percent(value: number, total: number): string | null {
    if (!total) {
      return null;
    }
    return `${Math.round((value / total) * 100)}%`;
  }

  private operationalErrorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return 'El servicio operacional no respondio correctamente.';
    }
    if (error.status === 401) {
      return 'Tu sesion expiro o no pudo validarse con operational. Vuelve a iniciar sesion.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a las métricas de esta empresa.';
    }
    if (error.status === 404) {
      return 'El entorno operacional del tenant aun no esta provisionado.';
    }
    return 'El servicio operacional no respondio correctamente.';
  }
}
