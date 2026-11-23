import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AgentCoreService } from '@domains/agents/data-access';
import { BusinessContextStatus, DocumentRead, TemplateRead } from '@domains/agents/domain';
import { AgentSimulatorPanelComponent } from '@domains/agents/ui/agent-simulator-panel/agent-simulator-panel.component';
import { ContextSummaryPanelComponent } from '@domains/agents/ui/context-summary-panel/context-summary-panel.component';
import { ContextUploadPanelComponent } from '@domains/agents/ui/context-upload-panel/context-upload-panel.component';
import { AlertComponent, PageHeaderComponent, TabItem, TabsComponent } from '@shared/ui';

type ContextTab = 'summary' | 'upload' | 'simulator';

@Component({
  selector: 'flowkron-business-context-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    PageHeaderComponent,
    TabsComponent,
    AlertComponent,
    ContextSummaryPanelComponent,
    ContextUploadPanelComponent,
    AgentSimulatorPanelComponent
  ],
  templateUrl: './business-context-page.component.html',
  styleUrl: './business-context-page.component.css'
})
export class BusinessContextPageComponent implements OnInit {
  private readonly agentService = inject(AgentCoreService);
  private readonly destroyRef = inject(DestroyRef);

  readonly activeTab = signal<ContextTab>('summary');
  readonly errorMsg = signal('');

  readonly contextStatus = signal<BusinessContextStatus | null>(null);
  readonly documents = signal<DocumentRead[]>([]);
  readonly templates = signal<TemplateRead[]>([]);
  readonly statusLoading = signal(false);
  readonly statusError = signal('');
  readonly templatesLoading = signal(false);
  readonly templatesError = signal('');

  readonly tabs: readonly TabItem[] = [
    { id: 'summary', label: 'Resumen' },
    { id: 'upload', label: 'Documentos' },
    { id: 'simulator', label: 'Simulador' }
  ];

  readonly hasDraftDocuments = computed(
    () => Boolean(this.contextStatus()?.document_actions?.patch) && this.documents().some((doc) => doc.status === 'draft')
  );

  ngOnInit(): void {
    this.loadAllData();
  }

  setTab(tab: string): void {
    if (tab === 'summary' || tab === 'upload' || tab === 'simulator') {
      this.activeTab.set(tab);
    }
  }

  loadAllData(): void {
    this.statusLoading.set(true);
    this.statusError.set('');
    this.agentService
      .getBusinessContextStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status) => {
          this.contextStatus.set(status);
          this.documents.set(status.documents ?? []);
          this.statusLoading.set(false);
        },
        error: () => {
          this.contextStatus.set(null);
          this.documents.set([]);
          this.statusLoading.set(false);
          const msg = 'No se pudo obtener el estado real del contexto empresarial desde flowkron-agent-core.';
          this.statusError.set(msg);
          this.errorMsg.set(msg);
        }
      });

    this.templatesLoading.set(true);
    this.templatesError.set('');
    this.agentService
      .listTemplates()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (tpls) => {
          this.templates.set(tpls);
          this.templatesLoading.set(false);
        },
        error: () => {
          this.templates.set([]);
          this.templatesLoading.set(false);
          const msg = 'No se pudieron cargar las plantillas desde flowkron-agent-core. Revisa que el core esté activo.';
          this.templatesError.set(msg);
          this.errorMsg.set(msg);
        }
      });
  }

  handleUploaded(): void {
    this.loadAllData();
    this.activeTab.set('summary');
  }

  deleteDoc(id: number): void {
    if (!this.contextStatus()?.document_actions?.delete) {
      this.errorMsg.set('El backend aún no permite eliminar documentos en este modo.');
      return;
    }
    this.agentService
      .deleteDocument(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => this.loadAllData(),
        error: () => this.errorMsg.set('No se pudo eliminar el documento. Revisa si el backend permite esta acción.')
      });
  }

  publishChanges(): void {
    if (!this.contextStatus()?.document_actions?.patch) return;
    const drafts = this.documents().filter((d) => d.status === 'draft');
    if (drafts.length === 0) {
      this.errorMsg.set('No hay documentos borrador pendientes de publicación.');
      return;
    }

    drafts.forEach((d) => {
      this.agentService
        .patchDocument(d.id, { status: 'active' })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => this.loadAllData(),
          error: () => this.errorMsg.set('No pudimos publicar un borrador. Revisa si el backend permite actualizar documentos.')
        });
    });
  }
}
