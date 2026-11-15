import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpEventType } from '@angular/common/http';
import {
  LucideUpload,
  LucideFileText,
  LucideDownload,
  LucideBot,
  LucideMessageSquare,
  LucidePlus,
  LucideTrash2,
  LucideSend,
  LucideInfo,
  LucideAlertTriangle,
  LucideBookOpen
} from '@lucide/angular';
import { AgentCoreService } from '@domains/agents/data-access';
import {
  BusinessContextStatus,
  DocumentRead,
  TemplateRead,
  AgentSource
} from '@domains/agents/domain';

type UploadState = 'idle' | 'selected' | 'validating' | 'uploading' | 'received' | 'processing' | 'success' | 'error';

@Component({
  selector: 'flowkron-business-context-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    LucideUpload,
    LucideFileText,
    LucideDownload,
    LucideBot,
    LucideMessageSquare,
    LucidePlus,
    LucideTrash2,
    LucideSend,
    LucideInfo,
    LucideAlertTriangle,
    LucideBookOpen
  ],
  templateUrl: './business-context-page.component.html',
  styleUrl: './business-context-page.component.css'
})
export class BusinessContextPageComponent implements OnInit, OnDestroy {
  private readonly agentService = inject(AgentCoreService);

  activeTab: 'summary' | 'upload' | 'simulator' = 'summary';
  uploadMethod: 'file' | 'template' | 'ai' = 'file';
  errorMsg = '';

  // Core Data
  contextStatus: BusinessContextStatus | null = null;
  documents: DocumentRead[] = [];
  templates: TemplateRead[] = [];
  statusLoading = false;
  statusError = '';
  templatesLoading = false;
  templatesError = '';

  // Config Percentage calculation
  configPercentage = 0;
  progressOffset = 251.2; // full ring circle dash offset
  lastUpdateText = 'Nunca';

  // File Upload State
  fileUploadTitle = '';
  selectedFile: File | null = null;
  uploadState: UploadState = 'idle';
  uploadProgress = 0;
  uploadMessage = 'Selecciona un documento para cargar contexto real al agente.';
  uploadError = '';
  readonly allowedUploadExtensions = ['.txt', '.md', '.docx', '.pdf'];
  readonly maxUploadBytes = 5 * 1024 * 1024;
  private uploadProgressTimer: ReturnType<typeof setInterval> | null = null;

  // AI Onboarding Assistant State
  aiCompanyName = '';
  aiIndustry = '';
  aiSessionId = '';
  aiMessages: Array<{ id: string; sender: 'user' | 'bot'; text: string }> = [];
  aiInput = '';
  aiLoading = false;

  // Simulator State
  simMessages: Array<{ id: string; sender: 'user' | 'bot'; text: string; confidence?: number; requiresHuman?: boolean; sources?: AgentSource[]; actions?: any[] }> = [];
  simInput = '';
  simLoading = false;
  selectedMessage: any = null;

  // Correction Modal State
  correctionOpen = false;
  newRuleName = '';
  newRuleContent = '';

  ngOnInit(): void {
    this.loadAllData();
  }

  ngOnDestroy(): void {
    this.stopUploadProgressFallback();
  }

  setTab(tab: 'summary' | 'upload' | 'simulator'): void {
    this.activeTab = tab;
  }

  getDownloadOption(template: TemplateRead, format: 'docx' | 'pdf'): TemplateRead['download_options'][number] | undefined {
    return (template.download_options ?? []).find((option) => option.format === format);
  }

  get activeDocumentsCount(): number {
    return this.contextStatus?.active_documents_count ?? 0;
  }

  get hasDraftDocuments(): boolean {
    return !!this.contextStatus?.document_actions?.patch && this.documents.some((document) => document.status === 'draft');
  }

  get canDeleteDocuments(): boolean {
    return !!this.contextStatus?.document_actions?.delete;
  }

  get agentStatusLabel(): string {
    switch (this.contextStatus?.agent_status) {
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
  }

  get agentStatusDescription(): string {
    switch (this.contextStatus?.agent_status) {
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
  }

  isAgentReady(): boolean {
    return this.contextStatus?.agent_status === 'trained' || this.contextStatus?.agent_status === 'active';
  }

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

  isDocumentSuccess(doc: DocumentRead): boolean {
    return doc.status === 'active';
  }

  isDocumentWarning(doc: DocumentRead): boolean {
    return ['draft', 'processing', 'pending', 'received', 'uploading'].includes(doc.status);
  }

  isDocumentError(doc: DocumentRead): boolean {
    return ['rejected', 'error', 'deprecated'].includes(doc.status);
  }

  documentType(doc: DocumentRead): string {
    return doc.content_type || this.extensionFromFilename(doc.filename).toUpperCase() || 'No disponible';
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) {
      return 'No disponible';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return 'No disponible';
    }
    return new Intl.DateTimeFormat('es-CL', {
      dateStyle: 'medium',
      timeStyle: 'short'
    }).format(date);
  }

  get uploadStatusLabel(): string {
    const labels: Record<UploadState, string> = {
      idle: 'Esperando archivo',
      selected: 'Archivo seleccionado',
      validating: 'Validando archivo',
      uploading: 'Subiendo documento',
      received: 'Documento recibido',
      processing: 'Procesando contenido',
      success: 'Documento aceptado',
      error: 'Error al subir'
    };
    return labels[this.uploadState];
  }

  shouldShowUploadProgress(): boolean {
    return ['validating', 'uploading', 'received', 'processing', 'success'].includes(this.uploadState);
  }

  extensionFromFilename(filename: string): string {
    const match = filename.toLowerCase().match(/\.[a-z0-9]+$/);
    return match?.[0] ?? '';
  }

  humanFileSize(size: number): string {
    if (size >= 1024 * 1024) {
      return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.max(Math.round(size / 1024), 1)} KB`;
  }

  private validateSelectedFile(): boolean {
    if (!this.selectedFile) {
      this.setUploadError('Selecciona un archivo antes de cargarlo.');
      return false;
    }
    if (!this.fileUploadTitle.trim()) {
      this.setUploadError('Ingresa un título claro para identificar el documento.');
      return false;
    }
    const extension = this.extensionFromFilename(this.selectedFile.name);
    if (!this.allowedUploadExtensions.includes(extension)) {
      this.setUploadError('El archivo no tiene un formato permitido. Usa PDF, Word, TXT o Markdown.');
      return false;
    }
    if (this.selectedFile.size <= 0) {
      this.setUploadError('El archivo está vacío. Selecciona un documento con contenido.');
      return false;
    }
    if (this.selectedFile.size > this.maxUploadBytes) {
      this.setUploadError(`El archivo supera el tamaño máximo permitido (${this.humanFileSize(this.maxUploadBytes)}).`);
      return false;
    }
    return true;
  }

  private setUploadError(message: string): void {
    this.stopUploadProgressFallback();
    this.uploadState = 'error';
    this.uploadProgress = 0;
    this.uploadError = message;
    this.uploadMessage = 'Corrige el problema y vuelve a intentarlo.';
  }

  private startUploadProgressFallback(): void {
    this.stopUploadProgressFallback();
    this.uploadProgressTimer = setInterval(() => {
      if (this.uploadState !== 'uploading') {
        this.stopUploadProgressFallback();
        return;
      }
      if (this.uploadProgress < 90) {
        this.uploadProgress = Math.min(this.uploadProgress + 7, 90);
      }
    }, 450);
  }

  private stopUploadProgressFallback(): void {
    if (this.uploadProgressTimer) {
      clearInterval(this.uploadProgressTimer);
      this.uploadProgressTimer = null;
    }
  }

  private messageFromBackendError(err: any): string {
    const detail = err?.error?.detail || err?.error?.title || err?.message;
    if (err?.status === 400) {
      return 'El archivo no tiene un formato permitido por el backend.';
    }
    if (err?.status === 413) {
      return 'El documento supera el tamaño máximo permitido. Reduce el tamaño del archivo e intenta nuevamente.';
    }
    if (err?.status === 422) {
      return detail || 'No pudimos extraer texto útil del documento. Revisa el contenido e intenta nuevamente.';
    }
    if (err?.status === 0) {
      return 'No pudimos conectar con flowkron-agent-core. Revisa que el backend esté disponible.';
    }
    return detail || 'No pudimos procesar el documento. Intenta nuevamente.';
  }

  loadAllData(): void {
    // 1. Context status and real backend documents
    this.statusLoading = true;
    this.statusError = '';
    this.agentService.getBusinessContextStatus().subscribe({
      next: (status) => {
        this.contextStatus = status;
        this.documents = status.documents ?? [];
        this.configPercentage = status.progress_percent ?? 0;
        this.progressOffset = 251.2 - (251.2 * this.configPercentage) / 100;
        this.lastUpdateText = this.formatDateTime(status.last_updated_at);
        this.statusLoading = false;
      },
      error: (err) => {
        this.contextStatus = null;
        this.documents = [];
        this.configPercentage = 0;
        this.progressOffset = 251.2;
        this.lastUpdateText = 'No disponible';
        this.statusLoading = false;
        this.statusError = 'No se pudo obtener el estado real del contexto empresarial desde flowkron-agent-core.';
        this.errorMsg = this.statusError;
        console.error(err);
        return;
      }
    });

    // 2. Templates
    this.templatesLoading = true;
    this.templatesError = '';
    this.agentService.listTemplates().subscribe({
      next: (tpls) => {
        this.templates = tpls;
        this.templatesLoading = false;
      },
      error: (err) => {
        this.templates = [];
        this.templatesLoading = false;
        this.templatesError = 'No se pudieron cargar las plantillas desde flowkron-agent-core. Revisa que el core este corriendo y actualizado.';
        this.errorMsg = this.templatesError;
        console.error(err);
        return;
      }
    });
  }

  calculateProgress(): void {
    this.configPercentage = this.contextStatus?.progress_percent ?? 0;
    this.progressOffset = 251.2 - (251.2 * this.configPercentage) / 100;
    this.lastUpdateText = this.formatDateTime(this.contextStatus?.last_updated_at ?? null);
  }

  deleteDoc(id: number): void {
    if (!this.canDeleteDocuments) {
      this.errorMsg = 'El backend aún no permite eliminar documentos en este modo.';
      return;
    }
    this.agentService.deleteDocument(id).subscribe({
      next: () => {
        this.loadAllData();
      },
      error: (err) => {
        this.errorMsg = 'No se pudo eliminar el documento. Revisa si el backend permite esta acción.';
        console.error(err);
      }
    });
  }

  // --- TAB 2: UPLOAD METHODS ---
  onFileSelected(event: any): void {
    const file = event.target.files?.[0];
    if (file) {
      this.selectedFile = file;
      this.uploadState = 'selected';
      this.uploadProgress = 0;
      this.uploadError = '';
      this.uploadMessage = `Seleccionaste ${file.name} (${this.humanFileSize(file.size)}).`;
    } else {
      this.clearSelectedFile();
    }
  }

  clearSelectedFile(): void {
    if (this.uploadState === 'uploading') {
      return;
    }
    this.stopUploadProgressFallback();
    this.selectedFile = null;
    this.uploadState = 'idle';
    this.uploadProgress = 0;
    this.uploadError = '';
    this.uploadMessage = 'Selecciona un documento para cargar contexto real al agente.';
  }

  submitFile(): void {
    this.stopUploadProgressFallback();
    this.uploadState = 'validating';
    this.uploadProgress = 5;
    this.uploadMessage = 'Validando formato y tamaño antes de enviar al backend.';
    this.uploadError = '';
    if (!this.validateSelectedFile() || !this.selectedFile) {
      return;
    }
    this.uploadState = 'uploading';
    this.uploadProgress = 12;
    this.uploadMessage = 'Enviando documento a flowkron-agent-core.';
    this.startUploadProgressFallback();
    this.agentService.uploadDocumentFileEvents(this.selectedFile, this.fileUploadTitle.trim(), 'active', 100).subscribe({
      next: (event) => {
        if (event.type === HttpEventType.Sent) {
          this.uploadProgress = Math.max(this.uploadProgress, 15);
          return;
        }
        if (event.type === HttpEventType.UploadProgress) {
          this.uploadProgress = event.total
            ? Math.min(Math.max(Math.round((event.loaded / event.total) * 95), this.uploadProgress), 95)
            : Math.max(this.uploadProgress, 35);
          return;
        }
        if (event.type === HttpEventType.Response) {
          this.stopUploadProgressFallback();
          this.uploadState = 'received';
          this.uploadProgress = 100;
          this.uploadMessage = 'El backend recibió el documento y respondió correctamente.';
          if (event.body?.data) {
            this.uploadState = 'success';
            this.uploadMessage = 'Documento aceptado. Actualizando el estado real del contexto empresarial.';
            this.fileUploadTitle = '';
            this.selectedFile = null;
            this.loadAllData();
            this.setTab('summary');
          }
        }
      },
      error: (err) => {
        this.stopUploadProgressFallback();
        this.setUploadError(this.messageFromBackendError(err));
        this.errorMsg = this.uploadError;
        console.error(err);
      }
    });
  }

  downloadTpl(id: number | undefined): void {
    if (!id) {
      return;
    }
    this.agentService.downloadTemplate(id).subscribe({
      next: ({ blob, filename }) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: (err) => {
        this.errorMsg = 'Error al descargar la plantilla.';
        console.error(err);
      }
    });
  }

  // --- TAB 2: AI ASSISTANT ---
  startAiSession(): void {
    this.aiLoading = true;
    this.agentService.createSetupSession(this.aiCompanyName, this.aiIndustry).subscribe({
      next: (session) => {
        this.aiSessionId = session.session_id;
        this.aiMessages = [
          { id: '1', sender: 'bot', text: `¡Hola! Soy tu asistente de configuración de Flowkron para ${this.aiCompanyName}.` },
          { id: '2', sender: 'bot', text: session.next_question }
        ];
        this.aiLoading = false;
      },
      error: (err) => {
        this.errorMsg = 'No se pudo iniciar la sesión de configuración con la IA.';
        this.aiLoading = false;
        console.error(err);
      }
    });
  }

  sendAiMessage(): void {
    if (!this.aiInput || this.aiLoading) return;
    const userText = this.aiInput;
    this.aiMessages.push({ id: Math.random().toString(), sender: 'user', text: userText });
    this.aiInput = '';
    this.aiLoading = true;

    this.agentService.sendSetupMessage(this.aiSessionId, userText).subscribe({
      next: (res) => {
        this.aiMessages.push({ id: Math.random().toString(), sender: 'bot', text: res.next_question });
        this.aiLoading = false;
      },
      error: (err) => {
        this.aiMessages.push({ id: Math.random().toString(), sender: 'bot', text: 'Tuvimos un error conectando con la IA. ¿Puedes volver a intentar?' });
        this.aiLoading = false;
        console.error(err);
      }
    });
  }

  generateAiContext(): void {
    this.aiLoading = true;
    this.agentService.generateContext(this.aiSessionId).subscribe({
      next: (res) => {
        // Success
        this.aiMessages.push({ id: Math.random().toString(), sender: 'bot', text: `He generado este resumen estructurado para revisión:\n${res.summary}\nCuando el backend entregue persistencia automática del asistente, se podrá incorporar al contexto empresarial.` });
        this.aiLoading = false;
        this.loadAllData(); // reload
      },
      error: (err) => {
        this.errorMsg = 'Error al consolidar la información del asistente de IA.';
        this.aiLoading = false;
        console.error(err);
      }
    });
  }
  // --- TAB 4: SIMULATOR ---
  sendSimMessage(): void {
    if (!this.simInput || this.simLoading) return;
    const text = this.simInput;
    this.simMessages.push({ id: Math.random().toString(), sender: 'user', text });
    this.simInput = '';
    this.simLoading = true;

    this.agentService.simulate({
      channel: 'webchat',
      conversation_id: 'sim-session-1',
      customer: { external_id: 'sim-user' },
      message: { type: 'text', content: text, attachments: [] },
      metadata: { raw_payload: {} }
    }).subscribe({
      next: (res) => {
        const botMsg = {
          id: Math.random().toString(),
          sender: 'bot' as const,
          text: res.reply.content,
          confidence: res.confidence,
          requiresHuman: res.requires_human,
          sources: res.sources,
          actions: res.actions
        };
        this.simMessages.push(botMsg);
        this.selectMessage(botMsg);
        this.simLoading = false;
      },
      error: (err) => {
        this.simMessages.push({
          id: Math.random().toString(),
          sender: 'bot',
          text: 'Error de simulación. El core no respondió de forma correcta. Revisa la conectividad en el puerto 8002.'
        });
        this.simLoading = false;
        console.error(err);
      }
    });
  }

  selectMessage(msg: any): void {
    if (msg.sender === 'bot') {
      this.selectedMessage = msg;
    }
  }

  publishChanges(): void {
    // Activate draft documents through flowkron-agent-core.
    if (!this.contextStatus?.document_actions?.patch || this.documents.length === 0) return;
    const drafts = this.documents.filter(d => d.status === 'draft');
    if (drafts.length === 0) {
      this.errorMsg = 'No hay documentos borrador pendientes de publicación.';
      return;
    }

    drafts.forEach(d => {
      this.agentService.patchDocument(d.id, { status: 'active' }).subscribe({
        next: () => {
          this.loadAllData();
        },
        error: (err) => {
          this.errorMsg = 'No pudimos publicar un borrador. Revisa si el backend permite actualizar documentos.';
          console.error(err);
        }
      });
    });
  }

  openCorrectionModal(): void {
    if (!this.selectedMessage) return;
    this.newRuleName = `Corrección para: "${this.simMessages[this.simMessages.length - 2]?.text || 'pregunta'}"`;
    this.newRuleContent = '';
    this.correctionOpen = true;
  }

  saveCorrection(): void {
    this.agentService.createRule({
      name: this.newRuleName,
      rule_type: 'correction',
      content: this.newRuleContent,
      priority: 10,
      is_active: true
    }).subscribe({
      next: () => {
        this.errorMsg = '';
        this.correctionOpen = false;
        this.newRuleName = '';
        this.newRuleContent = '';
      },
      error: (err) => {
        this.errorMsg = 'Error al crear la regla. Verifica la persistencia en el core.';
        console.error(err);
      }
    });
  }
}
