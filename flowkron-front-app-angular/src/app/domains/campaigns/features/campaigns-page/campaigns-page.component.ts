import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  CampaignSummary,
  CampaignsApiService,
  ChannelConnection
} from '@domains/campaigns/data-access/campaigns-api.service';

@Component({
  selector: 'flowkron-campaigns-page',
  standalone: true,
  template: `
    <section class="page-section">
      <header class="heading">
        <div>
          <h1>Campañas y canales</h1>
          <p class="muted">Administra conexiones de correo delegadas, plantillas aprobadas y campañas con envío stub/sandbox.</p>
        </div>
        <button class="btn btn-secondary" type="button" [disabled]="busy()" (click)="loadConnections()">Actualizar</button>
      </header>

      @if (notice(); as msg) {
        <p class="muted" [attr.role]="msg.error ? 'alert' : 'status'" style="margin-block:12px">{{ msg.text }}</p>
      }

      <section class="card glass-surface" style="padding:16px;margin-bottom:16px;display:grid;gap:12px">
        <h2>Conexiones de correo delegadas</h2>
        @if (canManage()) {
          <form style="display:flex;flex-wrap:wrap;gap:8px;align-items:end" (submit)="$event.preventDefault(); createEmailConnection()">
            <label style="display:grid;gap:4px">
              <small class="muted">Remitente</small>
              <input #senderInput type="email" required placeholder="noticias@empresa.test" [value]="senderAddress()" (input)="senderAddress.set(senderInput.value)">
            </label>
            <label style="display:grid;gap:4px">
              <small class="muted">Nombre visible</small>
              <input #displayInput type="text" required placeholder="Equipo Comercial" [value]="displayName()" (input)="displayName.set(displayInput.value)">
            </label>
            <label style="display:grid;gap:4px">
              <small class="muted">Proveedor</small>
              <select #provSelect [value]="provider()" (change)="provider.set($any(provSelect.value))">
                <option value="stub">Stub (demo/prueba)</option>
                <option value="resend">Resend (sandbox)</option>
              </select>
            </label>
            <button class="btn btn-primary" type="submit" [disabled]="busy() || !senderAddress().trim() || !displayName().trim()">
              Crear conexión
            </button>
          </form>
        }
        @for (conn of connections(); track conn.id) {
          <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:center;padding-top:8px;border-top:1px solid var(--border-subtle, rgba(148,163,184,.2))">
            <div>
              <strong>#{{ conn.id }} · {{ conn.display_name }}</strong>
              <small class="muted"> · {{ conn.sender_address }} · {{ conn.provider }} · {{ conn.status }} (v{{ conn.credential_version }})</small>
            </div>
            @if (canManage() && conn.status !== 'revoked') {
              <button class="btn btn-secondary" type="button" [disabled]="busy()" (click)="revoke(conn.id)">Revocar</button>
            }
          </div>
        } @empty {
          <p class="muted">Aún no hay conexiones de correo configuradas.</p>
        }
      </section>

      @if (canManage()) {
        <section class="card glass-surface" style="padding:16px;display:grid;gap:12px">
          <h2>Lanzar campaña rápida de correo (modo stub)</h2>
          <form style="display:grid;gap:10px" (submit)="$event.preventDefault(); launchQuickCampaign()">
            <div style="display:flex;flex-wrap:wrap;gap:10px">
              <label style="display:grid;gap:4px;flex:1;min-width:200px">
                <small class="muted">Nombre de campaña</small>
                <input #campName type="text" required placeholder="Novedades de temporada" [value]="campaignName()" (input)="campaignName.set(campName.value)">
              </label>
              <label style="display:grid;gap:4px;flex:1;min-width:200px">
                <small class="muted">Asunto del correo</small>
                <input #subjInput type="text" required placeholder="Tenemos novedades para ti" [value]="subject()" (input)="subject.set(subjInput.value)">
              </label>
              <label style="display:grid;gap:4px">
                <small class="muted">Conexión</small>
                <select #connSel [value]="selectedConnectionId()" (change)="selectedConnectionId.set(connSel.value)">
                  <option value="">Selecciona una conexión…</option>
                  @for (conn of activeEmailConnections(); track conn.id) {
                    <option [value]="conn.id">#{{ conn.id }} · {{ conn.sender_address }} ({{ conn.provider }})</option>
                  }
                </select>
              </label>
            </div>
            <label style="display:grid;gap:4px">
              <small class="muted">Contenido de texto</small>
              <textarea #bodyInput rows="3" required placeholder="Hola, te compartimos nuestras novedades…" [value]="bodyText()" (input)="bodyText.set(bodyInput.value)"></textarea>
            </label>
            <div style="display:flex;flex-wrap:wrap;gap:8px">
              <button class="btn btn-primary" type="submit" [disabled]="busy() || !campaignName().trim() || !subject().trim() || !bodyText().trim() || !selectedConnectionId()">
                Crear y aprobar campaña
              </button>
              <button class="btn btn-secondary" type="button" [disabled]="busy()" (click)="dispatchStubBatch()">
                Ejecutar worker stub
              </button>
            </div>
          </form>

          @if (lastCampaign(); as camp) {
            <p class="muted" role="status">
              Última campaña #{{ camp.id }} ({{ camp.name }}): estado <strong>{{ camp.status }}</strong> · v{{ camp.version }}
            </p>
          }
        </section>
      }
    </section>
  `
})
export class CampaignsPageComponent implements OnInit {
  private readonly api = inject(CampaignsApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connections = signal<ChannelConnection[]>([]);
  readonly activeEmailConnections = computed(() =>
    this.connections().filter((c) => c.channel === 'email' && c.status === 'active' && c.verified)
  );
  readonly busy = signal(false);
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly lastCampaign = signal<CampaignSummary | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly senderAddress = signal('');
  readonly displayName = signal('');
  readonly provider = signal<'stub' | 'resend'>('stub');

  readonly campaignName = signal('');
  readonly subject = signal('');
  readonly bodyText = signal('');
  readonly selectedConnectionId = signal('');

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
    if (this.busy()) return;
    this.busy.set(true);
    this.notice.set(null);
    this.api.createConnection({
      channel: 'email',
      provider: this.provider(),
      sender_address: this.senderAddress().trim(),
      display_name: this.displayName().trim(),
      verified: true,
      sandbox_only: true
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.senderAddress.set('');
        this.displayName.set('');
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
    const connId = Number(this.selectedConnectionId());
    if (this.busy() || !Number.isSafeInteger(connId) || connId < 1) return;
    this.busy.set(true);
    this.notice.set(null);
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    this.api.createTemplate({
      name: `Plantilla · ${this.campaignName().trim()}`,
      channel: 'email',
      subject: this.subject().trim(),
      body_text: this.bodyText().trim(),
      approve_immediately: true
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (tmpl) => {
        this.api.createCampaign({
          name: this.campaignName().trim(),
          channel: 'email',
          purpose: 'marketing',
          template_version_id: tmpl.template_version_id,
          connection_id: connId,
          timezone_iana: tz
        }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: (camp) => {
            this.api.approveCampaign(camp.id, camp.version).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
              next: (approved) => {
                this.lastCampaign.set(approved);
                this.campaignName.set('');
                this.subject.set('');
                this.bodyText.set('');
                this.busy.set(false);
                this.notice.set({ error: false, text: `Campaña #${approved.id} aprobada con snapshot listo.` });
              },
              error: () => {
                this.busy.set(false);
                this.notice.set({ error: true, text: 'La campaña se creó pero no pudo aprobarse.' });
              }
            });
          },
          error: () => {
            this.busy.set(false);
            this.notice.set({ error: true, text: 'No pudimos crear la campaña.' });
          }
        });
      },
      error: () => {
        this.busy.set(false);
        this.notice.set({ error: true, text: 'No pudimos validar/crear la plantilla.' });
      }
    });
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
