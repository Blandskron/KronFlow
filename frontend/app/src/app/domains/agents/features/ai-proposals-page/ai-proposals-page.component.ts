import { DatePipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AIProposalItem, AIProposalsApiService } from '@domains/agents/data-access/ai-proposals-api.service';
import {
  AlertComponent,
  BadgeComponent,
  BadgeTone,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent
} from '@shared/ui';

@Component({
  selector: 'kronflow-ai-proposals-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, JsonPipe, PageHeaderComponent, AlertComponent, BadgeComponent, EmptyStateComponent, SkeletonComponent],
  templateUrl: './ai-proposals-page.component.html',
  styleUrl: './ai-proposals-page.component.css'
})
export class AIProposalsPageComponent implements OnInit {
  private readonly api = inject(AIProposalsApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly items = signal<AIProposalItem[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly statusFilter = signal('pending');
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly statuses = [
    { id: 'pending', label: 'Pendientes' },
    { id: 'approved', label: 'Aprobadas' },
    { id: 'executed', label: 'Ejecutadas' },
    { id: 'rejected', label: 'Rechazadas' },
    { id: 'expired', label: 'Expiradas' }
  ];

  readonly statusTones: Record<string, BadgeTone> = {
    pending: 'warning',
    approved: 'info',
    executed: 'success',
    rejected: 'danger',
    expired: 'neutral'
  };

  ngOnInit(): void {
    this.reload();
  }

  setStatus(status: string): void {
    this.statusFilter.set(status);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.list(this.statusFilter()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (page) => {
        this.items.set(page.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.notice.set({ error: true, text: 'No pudimos cargar las propuestas IA.' });
      }
    });
  }

  approve(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api
      .approve(item.id, item.proposal_version, 'Aprobada desde CRM')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ error: false, text: `Propuesta #${item.id} aprobada.` });
          this.reload();
        },
        error: (err: HttpErrorResponse) => this.handleMutationError(err)
      });
  }

  reject(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api
      .reject(item.id, item.proposal_version, 'Rechazada desde CRM')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ error: false, text: `Propuesta #${item.id} rechazada.` });
          this.reload();
        },
        error: (err: HttpErrorResponse) => this.handleMutationError(err)
      });
  }

  execute(item: AIProposalItem): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api
      .execute(item.id, item.proposal_version)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ error: false, text: `Propuesta #${item.id} ejecutada.` });
          this.reload();
        },
        error: (err: HttpErrorResponse) => this.handleMutationError(err)
      });
  }

  private handleMutationError(err: HttpErrorResponse): void {
    this.busy.set(false);
    this.notice.set({
      error: true,
      text: err.status === 409 ? 'La propuesta cambió o expiró. Recargando…' : 'No pudimos procesar la propuesta.'
    });
    if (err.status === 409) this.reload();
  }
}
