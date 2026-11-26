import { DatePipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { ToolHubApiService } from '@domains/agents/data-access';
import {
  ChannelWebhookRouteItem,
  CommerceOrderItem,
  ExternalMappingItem,
  RemoteMcpServerItem,
  ToolDefinitionItem,
  ToolEffectMode,
  ToolInvocationItem,
  VoiceCallItem,
  WebchatWidgetItem
} from '@domains/agents/domain';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  AlertComponent,
  BadgeComponent,
  BadgeTone,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent,
  TabItem,
  TabsComponent
} from '@shared/ui';

@Component({
  selector: 'kronflow-tools-hub-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    JsonPipe,
    ReactiveFormsModule,
    PageHeaderComponent,
    TabsComponent,
    AlertComponent,
    BadgeComponent,
    EmptyStateComponent,
    SkeletonComponent
  ],
  templateUrl: './tools-hub-page.component.html',
  styleUrl: './tools-hub-page.component.css'
})
export class ToolsHubPageComponent implements OnInit {
  private readonly api = inject(ToolHubApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly tabs: readonly TabItem[] = [
    { id: 'tools', label: 'Herramientas' },
    { id: 'webchat', label: 'Webchat embebible' },
    { id: 'integrations', label: 'Integraciones y MCP' },
    { id: 'commerce_voice', label: 'Comercio, Voz y MCP remoto' }
  ];
  readonly activeTab = signal<'tools' | 'webchat' | 'integrations' | 'commerce_voice'>('tools');
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly tools = signal<ToolDefinitionItem[]>([]);
  readonly invocations = signal<ToolInvocationItem[]>([]);
  readonly widgets = signal<WebchatWidgetItem[]>([]);
  readonly webhookRoutes = signal<ChannelWebhookRouteItem[]>([]);
  readonly mappings = signal<ExternalMappingItem[]>([]);
  readonly remoteMcpServers = signal<RemoteMcpServerItem[]>([]);
  readonly commerceOrders = signal<CommerceOrderItem[]>([]);
  readonly voiceCalls = signal<VoiceCallItem[]>([]);
  readonly mcpToolsOutput = signal<Record<string, unknown> | null>(null);
  readonly selectedToolKey = signal<string>('crm.contact.lookup');
  readonly selectedWidgetId = signal<number | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly notice = signal<{ tone: 'success' | 'danger' | 'info'; text: string } | null>(null);

  readonly selectedWidget = computed(
    () => this.widgets().find((item) => item.id === this.selectedWidgetId()) ?? null
  );

  readonly effectTones: Record<string, BadgeTone> = {
    read_only: 'info',
    proposal_required: 'warning',
    outbox_async: 'success'
  };

  readonly statusTones: Record<string, BadgeTone> = {
    completed: 'success',
    proposed: 'warning',
    queued: 'info',
    rejected: 'danger',
    failed: 'danger'
  };

  readonly toolForm = this.fb.nonNullable.group({
    toolKey: ['', [Validators.required, Validators.maxLength(80)]],
    name: ['', [Validators.required, Validators.maxLength(160)]],
    description: ['', [Validators.maxLength(400)]],
    effectMode: ['read_only' as ToolEffectMode, [Validators.required]],
    inputSchemaJson: ['{\n  "type": "object",\n  "required": [],\n  "properties": {}\n}', [Validators.required]],
    maxCallsPerHour: [120, [Validators.required, Validators.min(1), Validators.max(5000)]]
  });

  readonly invokeForm = this.fb.nonNullable.group({
    toolKey: ['crm.contact.lookup', [Validators.required]],
    idempotencyKey: ['hub-test-1', [Validators.required, Validators.maxLength(180)]],
    argumentsJson: ['{\n  "client_id": 1\n}', [Validators.required]]
  });

  readonly widgetForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(160)]],
    allowedOriginsText: ['https://empresa.example', [Validators.required]],
    welcomeMessage: ['¡Hola! ¿En qué podemos ayudarte hoy?', [Validators.required, Validators.maxLength(300)]],
    isActive: [true]
  });

  readonly routeForm = this.fb.nonNullable.group({
    channel: [
      'instagram' as 'whatsapp' | 'instagram' | 'messenger' | 'shopify' | 'mercadopago' | 'voice_twilio',
      [Validators.required]
    ],
    externalAccountId: ['', [Validators.required, Validators.maxLength(120)]],
    verifyToken: ['', [Validators.required, Validators.minLength(6), Validators.maxLength(120)]],
    appSecret: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(160)]]
  });

  readonly remoteMcpForm = this.fb.nonNullable.group({
    serverKey: ['', [Validators.required, Validators.maxLength(64)]],
    name: ['', [Validators.required, Validators.maxLength(160)]],
    baseUrl: ['https://', [Validators.required, Validators.maxLength(500)]],
    allowedToolsText: ['crm.contact.lookup', [Validators.required]],
    authToken: ['']
  });

  readonly commerceOrderForm = this.fb.nonNullable.group({
    provider: ['mercadopago' as 'mercadopago' | 'shopify' | 'stub', [Validators.required]],
    currency: ['CLP', [Validators.required, Validators.minLength(3), Validators.maxLength(3)]],
    expectedAmountMinor: [19990, [Validators.required, Validators.min(1)]]
  });

  ngOnInit(): void {
    this.reloadAll();
  }

  setTab(tab: string): void {
    if (tab === 'tools' || tab === 'webchat' || tab === 'integrations' || tab === 'commerce_voice') {
      this.activeTab.set(tab);
    }
  }

  reloadAll(preferredWidgetId?: number | null): void {
    this.loading.set(true);
    forkJoin({
      tools: this.api.listTools(),
      invocations: this.api.listInvocations({ limit: 25 }),
      widgets: this.api.listWidgets(),
      webhookRoutes: this.api.listWebhookRoutes(),
      mappings: this.api.listMappings(),
      remoteMcpServers: this.api.listRemoteMcpServers(),
      commerceOrders: this.api.listCommerceOrders(),
      voiceCalls: this.api.listVoiceCalls()
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ tools, invocations, widgets, webhookRoutes, mappings, remoteMcpServers, commerceOrders, voiceCalls }) => {
          this.tools.set(tools);
          this.invocations.set(invocations);
          this.widgets.set(widgets);
          this.webhookRoutes.set(webhookRoutes);
          this.mappings.set(mappings);
          this.remoteMcpServers.set(remoteMcpServers);
          this.commerceOrders.set(commerceOrders);
          this.voiceCalls.set(voiceCalls);
          this.loading.set(false);
          if (tools.length && !tools.some((t) => t.tool_key === this.selectedToolKey())) {
            this.selectTool(tools[0]);
          }
          const targetId = preferredWidgetId ?? this.selectedWidgetId();
          const widgetMatch = (targetId ? widgets.find((w) => w.id === targetId) : null) ?? widgets[0] ?? null;
          if (widgetMatch) {
            this.selectWidget(widgetMatch);
          }
        },
        error: () => {
          this.loading.set(false);
          this.notice.set({ tone: 'danger', text: 'No pudimos cargar el Hub de herramientas y webchat.' });
        }
      });
  }

  selectTool(tool: ToolDefinitionItem): void {
    this.selectedToolKey.set(tool.tool_key);
    this.invokeForm.patchValue({
      toolKey: tool.tool_key,
      idempotencyKey: `hub-${Date.now()}`
    });
  }

  toggleTool(tool: ToolDefinitionItem): void {
    if (!this.canManage() || this.busy()) return;
    this.busy.set(true);
    this.api
      .updateTool(tool.id, { is_enabled: !tool.is_enabled })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({
            tone: 'success',
            text: `Herramienta "${tool.tool_key}" ${tool.is_enabled ? 'deshabilitada' : 'habilitada'}.`
          });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos actualizar la herramienta.')
      });
  }

  createTool(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.toolForm.invalid) {
      this.toolForm.markAllAsTouched();
      this.notice.set({ tone: 'danger', text: 'Revisa los campos requeridos de la herramienta.' });
      return;
    }
    const raw = this.toolForm.getRawValue();
    let schema: Record<string, unknown>;
    try {
      schema = JSON.parse(raw.inputSchemaJson) as Record<string, unknown>;
    } catch {
      this.notice.set({ tone: 'danger', text: 'El JSON Schema de entrada no es válido.' });
      return;
    }

    this.busy.set(true);
    this.api
      .createTool({
        tool_key: raw.toolKey.trim(),
        name: raw.name.trim(),
        description: raw.description.trim(),
        effect_mode: raw.effectMode,
        input_schema: schema,
        max_calls_per_hour: Number(raw.maxCallsPerHour)
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (created) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Herramienta "${created.tool_key}" registrada.` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos registrar la herramienta.')
      });
  }

  runInvocation(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.invokeForm.invalid) {
      this.invokeForm.markAllAsTouched();
      return;
    }
    const raw = this.invokeForm.getRawValue();
    let parsedArgs: Record<string, unknown>;
    try {
      parsedArgs = JSON.parse(raw.argumentsJson) as Record<string, unknown>;
    } catch {
      this.notice.set({ tone: 'danger', text: 'Los argumentos JSON no son válidos.' });
      return;
    }

    this.busy.set(true);
    const selectedTool = this.tools().find((t) => t.tool_key === raw.toolKey);
    this.api
      .invokeTool({
        tool_key: raw.toolKey,
        arguments: parsedArgs,
        idempotency_key: raw.idempotencyKey.trim(),
        expected_schema_version: selectedTool?.schema_version
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (inv) => {
          this.busy.set(false);
          this.notice.set({
            tone: 'success',
            text: `Invocación #${inv.id} (${inv.status})${inv.duplicate ? ' · reutilizada por idempotencia' : ''}.`
          });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'Falló la invocación gobernada.')
      });
  }

  selectWidget(widget: WebchatWidgetItem): void {
    this.selectedWidgetId.set(widget.id);
    this.widgetForm.reset({
      name: widget.name,
      allowedOriginsText: widget.allowed_origins.join('\n'),
      welcomeMessage: widget.welcome_message,
      isActive: widget.is_active
    });
  }

  startNewWidget(): void {
    this.selectedWidgetId.set(null);
    this.widgetForm.reset({
      name: '',
      allowedOriginsText: 'https://empresa.example',
      welcomeMessage: '¡Hola! ¿En qué podemos ayudarte hoy?',
      isActive: true
    });
  }

  saveWidget(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.widgetForm.invalid) {
      this.widgetForm.markAllAsTouched();
      this.notice.set({ tone: 'danger', text: 'Completa nombre, orígenes y mensaje de bienvenida.' });
      return;
    }
    const raw = this.widgetForm.getRawValue();
    const origins = raw.allowedOriginsText
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!origins.length) {
      this.notice.set({ tone: 'danger', text: 'Indica al menos un origen exacto (sin comodines).' });
      return;
    }

    const current = this.selectedWidget();
    this.busy.set(true);
    if (!current) {
      this.api
        .createWidget({
          name: raw.name.trim(),
          allowed_origins: origins,
          welcome_message: raw.welcomeMessage.trim(),
          is_active: raw.isActive
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (created) => {
            this.busy.set(false);
            this.notice.set({ tone: 'success', text: `Widget "${created.name}" creado.` });
            this.reloadAll(created.id);
          },
          error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos crear el widget webchat.')
        });
      return;
    }

    this.api
      .updateWidget(current.id, {
        name: raw.name.trim(),
        allowed_origins: origins,
        welcome_message: raw.welcomeMessage.trim(),
        is_active: raw.isActive
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Widget "${updated.name}" actualizado.` });
          this.reloadAll(updated.id);
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos actualizar el widget webchat.')
      });
  }

  embedSnippet(widget: WebchatWidgetItem): string {
    return `<script defer src="https://app.kronflow.local/webchat/widget.js" data-widget-key="${widget.widget_key}"></script>`;
  }

  createRoute(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.routeForm.invalid) {
      this.routeForm.markAllAsTouched();
      this.notice.set({ tone: 'danger', text: 'Completa canal, cuenta externa, verify token y app secret.' });
      return;
    }
    const raw = this.routeForm.getRawValue();
    this.busy.set(true);
    this.api
      .createWebhookRoute({
        channel: raw.channel,
        external_account_id: raw.externalAccountId.trim(),
        verify_token: raw.verifyToken.trim(),
        app_secret: raw.appSecret.trim()
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (created) => {
          this.busy.set(false);
          this.notice.set({
            tone: 'success',
            text: `Ruta Meta ${created.channel} (${created.external_account_id}) registrada.`
          });
          this.routeForm.reset({
            channel: raw.channel,
            externalAccountId: '',
            verifyToken: '',
            appSecret: ''
          });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos registrar la ruta webhook Meta.')
      });
  }

  deactivateRoute(route: ChannelWebhookRouteItem): void {
    if (!this.canManage() || this.busy() || !route.is_active) return;
    this.busy.set(true);
    this.api
      .deactivateWebhookRoute(route.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ tone: 'info', text: `Ruta ${route.channel} (${route.external_account_id}) desactivada.` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos desactivar la ruta webhook.')
      });
  }

  resolveMapping(mapping: ExternalMappingItem, resolution: 'synced' | 'disconnected'): void {
    if (!this.canManage() || this.busy()) return;
    this.busy.set(true);
    this.api
      .resolveMapping(mapping.id, resolution)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Mapeo #${updated.id} actualizado a "${updated.sync_state}".` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos resolver el conflicto de mapeo.')
      });
  }

  inspectMcp(): void {
    if (!this.canManage() || this.busy()) return;
    this.busy.set(true);
    this.api
      .callMcp('tools/list', {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.busy.set(false);
          this.mcpToolsOutput.set(res);
          this.notice.set({ tone: 'success', text: 'Catálogo MCP JSON-RPC 2.0 consultado correctamente.' });
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos consultar el servidor MCP.')
      });
  }

  registerRemoteMcp(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.remoteMcpForm.invalid) {
      this.remoteMcpForm.markAllAsTouched();
      this.notice.set({ tone: 'danger', text: 'Completa server_key, nombre, URL HTTPS y herramientas permitidas.' });
      return;
    }
    const raw = this.remoteMcpForm.getRawValue();
    const allowed = raw.allowedToolsText
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    this.busy.set(true);
    this.api
      .createRemoteMcpServer({
        server_key: raw.serverKey.trim(),
        name: raw.name.trim(),
        base_url: raw.baseUrl.trim(),
        allowed_tools: allowed,
        auth_token: raw.authToken.trim() || undefined
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (created) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Servidor MCP remoto "${created.server_key}" registrado.` });
          this.remoteMcpForm.reset({
            serverKey: '',
            name: '',
            baseUrl: 'https://',
            allowedToolsText: 'crm.contact.lookup',
            authToken: ''
          });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos registrar el servidor MCP remoto.')
      });
  }

  revokeRemoteMcp(server: RemoteMcpServerItem): void {
    if (!this.canManage() || this.busy() || !server.is_active) return;
    this.busy.set(true);
    this.api
      .revokeRemoteMcpServer(server.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ tone: 'info', text: `Servidor MCP "${server.server_key}" revocado.` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos revocar el servidor MCP remoto.')
      });
  }

  createOrder(): void {
    if (!this.canManage() || this.busy()) return;
    if (this.commerceOrderForm.invalid) {
      this.commerceOrderForm.markAllAsTouched();
      return;
    }
    const raw = this.commerceOrderForm.getRawValue();
    this.busy.set(true);
    this.api
      .createCommerceOrder({
        provider: raw.provider,
        currency: raw.currency.trim().toUpperCase(),
        expected_amount_minor: Number(raw.expectedAmountMinor)
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (order) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Orden ${order.order_number} creada (${order.currency}).` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos crear la orden comercial.')
      });
  }

  issueCheckoutLink(order: CommerceOrderItem): void {
    if (!this.canManage() || this.busy()) return;
    this.busy.set(true);
    this.api
      .createCheckoutLink(order.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.busy.set(false);
          this.notice.set({ tone: 'success', text: `Enlace emitido para ${updated.order_number}.` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos emitir el enlace de pago.')
      });
  }

  transferCall(call: VoiceCallItem): void {
    if (!this.canManage() || this.busy()) return;
    this.busy.set(true);
    this.api
      .transferVoiceCall(call.id, 'operator_requested_transfer')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.notice.set({ tone: 'info', text: `Llamada ${call.external_call_id} transferida a atención humana.` });
          this.reloadAll();
        },
        error: (err: HttpErrorResponse) => this.handleError(err, 'No pudimos transferir la llamada.')
      });
  }

  private handleError(err: HttpErrorResponse, fallback: string): void {
    this.busy.set(false);
    const detail = typeof err.error?.detail === 'string' ? err.error.detail : null;
    this.notice.set({ tone: 'danger', text: detail || fallback });
  }
}
