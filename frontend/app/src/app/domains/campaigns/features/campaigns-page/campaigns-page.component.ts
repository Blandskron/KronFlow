import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { switchMap } from 'rxjs';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  CampaignAudiencePreview,
  CampaignSummary,
  CampaignsApiService,
  ChannelConnection
} from '@domains/campaigns/data-access/campaigns-api.service';
import { AlertComponent, BadgeComponent, EmptyStateComponent, PageHeaderComponent } from '@shared/ui';

@Component({
  selector: 'kronflow-campaigns-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, PageHeaderComponent, AlertComponent, BadgeComponent, EmptyStateComponent],
  templateUrl: './campaigns-page.component.html',
  styleUrl: './campaigns-page.component.css'
})
export class CampaignsPageComponent implements OnInit {
  private readonly api = inject(CampaignsApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly connections = signal<ChannelConnection[]>([]);
  readonly activeEmailConnections = computed(() =>
    this.connections().filter((c) => c.channel === 'email' && c.status === 'active' && c.verified)
  );
  readonly busy = signal(false);
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly lastCampaign = signal<CampaignSummary | null>(null);
  readonly audiencePreview = signal<CampaignAudiencePreview | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly connectionForm = this.fb.nonNullable.group({
    senderAddress: ['', [Validators.required, Validators.email]],
    displayName: ['', [Validators.required, Validators.maxLength(120)]],
    provider: ['stub' as 'stub' | 'resend']
  });

  readonly campaignForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(160)]],
    subject: ['', [Validators.required, Validators.maxLength(200)]],
    connectionId: ['', [Validators.required]],
    bodyText: ['', [Validators.required, Validators.maxLength(4000)]]
  });

  ngOnInit(): void {
    this.loadConnections();
  }

  loadConnections(): void {
    this.api.listConnections().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (items) => this.connections.set(items),
      error: () => this.notice.set({ error: true, text: 'No pudimos cargar las conexiones de canal.' })
    });
  }

  createEmailConnection(): void {
    if (this.busy() || this.connectionForm.invalid) return;
    const raw = this.connectionForm.getRawValue();
    this.busy.set(true);
    this.notice.set(null);

    this.api
      .createConnection({
        channel: 'email',
        provider: raw.provider,
        sender_address: raw.senderAddress.trim(),
        display_name: raw.displayName.trim(),
        verified: true,
        sandbox_only: true
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.connectionForm.reset({ senderAddress: '', displayName: '', provider: 'stub' });
          this.busy.set(false);
          this.notice.set({ error: false, text: 'Conexión de correo creada y verificada.' });
          this.loadConnections();
        },
        error: () => {
          this.busy.set(false);
          this.notice.set({ error: true, text: 'No pudimos crear la conexión. Verifica el correo remitente.' });
        }
      });
  }

  revoke(connectionId: number): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.revokeConnection(connectionId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set({ error: false, text: `Conexión #${connectionId} revocada.` });
        this.loadConnections();
      },
      error: () => {
        this.busy.set(false);
        this.notice.set({ error: true, text: 'No pudimos revocar la conexión.' });
      }
    });
  }

  launchQuickCampaign(): void {
    if (this.busy() || this.campaignForm.invalid) return;
    const raw = this.campaignForm.getRawValue();
    const connId = Number(raw.connectionId);
    if (!Number.isSafeInteger(connId) || connId < 1) return;

    this.busy.set(true);
    this.notice.set(null);
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

    this.api
      .createTemplate({
        name: `Plantilla · ${raw.name.trim()}`,
        channel: 'email',
        subject: raw.subject.trim(),
        body_text: raw.bodyText.trim(),
        approve_immediately: true
      })
      .pipe(
        switchMap((tmpl) =>
          this.api.createCampaign({
            name: raw.name.trim(),
            channel: 'email',
            purpose: 'marketing',
            template_version_id: tmpl.template_version_id,
            connection_id: connId,
            timezone_iana: tz
          })
        ),
        switchMap((camp) => this.api.approveCampaign(camp.id, camp.version)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe({
        next: (approved) => {
          this.lastCampaign.set(approved);
          this.campaignForm.reset({ name: '', subject: '', connectionId: raw.connectionId, bodyText: '' });
          this.busy.set(false);
          this.notice.set({ error: false, text: `Campaña #${approved.id} aprobada con snapshot listo.` });
        },
        error: () => {
          this.busy.set(false);
          this.notice.set({ error: true, text: 'No pudimos crear y aprobar la campaña. Revisa la conexión y plantilla.' });
        }
      });
  }

  previewLastCampaign(): void {
    const camp = this.lastCampaign();
    if (!camp || this.busy()) return;
    this.busy.set(true);
    this.api.previewCampaign(camp.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.audiencePreview.set(res);
        this.busy.set(false);
        this.notice.set({
          error: false,
          text: `Previsualización campaña #${res.campaign_id}: ${res.eligible_count} elegibles, ${res.excluded_count} excluidos.`
        });
      },
      error: () => {
        this.busy.set(false);
        this.notice.set({ error: true, text: 'No pudimos previsualizar la audiencia de la campaña.' });
      }
    });
  }

  exclusionEntries(map: Record<string, number>): { reason: string; count: number }[] {
    return Object.entries(map).map(([reason, count]) => ({ reason, count }));
  }

  dispatchStubBatch(): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.dispatchStub().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.busy.set(false);
        this.notice.set({
          error: false,
          text: `Worker stub ejecutado: ${res.accepted} aceptados, ${res.suppressed} suprimidos, ${res.skipped_paused} pausados.`
        });
      },
      error: () => {
        this.busy.set(false);
        this.notice.set({ error: true, text: 'No pudimos ejecutar el despacho stub.' });
      }
    });
  }
}
