import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { LucideAlertTriangle, LucideFileText, LucideInfo, LucidePlus, LucideTrash2 } from '@lucide/angular';
import { BusinessContextStatus, DocumentRead } from '@domains/agents/domain';
import { AlertComponent, BadgeComponent, BadgeTone, EmptyStateComponent } from '@shared/ui';

@Component({
  selector: 'kronflow-context-summary-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    LucideAlertTriangle,
    LucideFileText,
    LucideInfo,
    LucidePlus,
    LucideTrash2,
    AlertComponent,
    BadgeComponent,
    EmptyStateComponent
  ],
  templateUrl: './context-summary-panel.component.html',
  styleUrl: './context-summary-panel.component.css'
})
export class ContextSummaryPanelComponent {
  readonly contextStatus = input<BusinessContextStatus | null>(null);
  readonly documents = input<readonly DocumentRead[]>([]);
  readonly loading = input(false);
  readonly error = input('');

  readonly goToUpload = output<void>();
  readonly deleteDocument = output<number>();

  readonly configPercentage = computed(() => this.contextStatus()?.progress_percent ?? 0);
  readonly progressOffset = computed(() => 251.2 - (251.2 * this.configPercentage()) / 100);
  readonly lastUpdateText = computed(() => this.formatDateTime(this.contextStatus()?.last_updated_at));
  readonly activeDocumentsCount = computed(() => this.contextStatus()?.active_documents_count ?? 0);
  readonly canDeleteDocuments = computed(() => Boolean(this.contextStatus()?.document_actions?.delete));
  readonly isAgentReady = computed(() => {
    const status = this.contextStatus()?.agent_status;
    return status === 'trained' || status === 'active';
  });

  readonly agentStatusLabel = computed(() => {
    switch (this.contextStatus()?.agent_status) {
      case 'trained':
      case 'active':
        return 'Entrenado con contexto activo';
      case 'pending':
        return 'Pendiente de completar contexto';
      case 'processing':
        return 'Procesando contexto';
      case 'error':
        return 'Requiere revisión';
      case 'not_configured':
      default:
        return 'Aún no entrenado';
    }
  });

  readonly agentStatusDescription = computed(() => {
    switch (this.contextStatus()?.agent_status) {
      case 'trained':
      case 'active':
        return 'El backend informa documentos activos para responder con contexto validado.';
      case 'pending':
        return 'Hay contexto cargado, pero aún faltan documentos recomendados para completar la configuración.';
      case 'processing':
        return 'El backend informa documentos en revisión o procesamiento.';
      case 'error':
        return 'Hay documentos con errores o rechazados. Revisa la tabla para corregirlos.';
      case 'not_configured':
      default:
        return 'Aún no has cargado documentos de contexto.';
    }
  });

  documentStatusLabel(status: DocumentRead['status']): string {
    const labels: Record<string, string> = {
      pending: 'Pendiente',
      uploading: 'Subiendo',
      received: 'Recibido',
      processing: 'Procesando',
      active: 'Activo',
      rejected: 'Rechazado',
      error: 'Error',
      draft: 'Borrador',
      deprecated: 'Deprecado'
    };
    return labels[status] ?? 'No disponible';
  }

  documentTone(doc: DocumentRead): BadgeTone {
    if (doc.status === 'active') return 'success';
    if (['draft', 'processing', 'pending', 'received', 'uploading'].includes(doc.status)) return 'warning';
    if (['rejected', 'error', 'deprecated'].includes(doc.status)) return 'danger';
    return 'neutral';
  }

  documentType(doc: DocumentRead): string {
    const ext = doc.filename.toLowerCase().match(/\.[a-z0-9]+$/)?.[0] ?? '';
    return doc.content_type || ext.toUpperCase() || 'No disponible';
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) return 'No disponible';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'No disponible';
    return new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }
}
