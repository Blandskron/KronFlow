import { HttpEventType } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnDestroy,
  computed,
  inject,
  input,
  output,
  signal
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { LucideBot, LucideDownload, LucideSend, LucideUpload } from '@lucide/angular';
import { extractHttpErrorMessage } from '@core/utils/http-error';
import { AgentCoreService } from '@domains/agents/data-access';
import { TemplateRead } from '@domains/agents/domain';
import { AlertComponent, EmptyStateComponent } from '@shared/ui';

type UploadMethod = 'file' | 'template' | 'ai';
type UploadState = 'idle' | 'selected' | 'validating' | 'uploading' | 'received' | 'processing' | 'success' | 'error';

interface AiChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
}

@Component({
  selector: 'flowkron-context-upload-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, LucideUpload, LucideDownload, LucideBot, LucideSend, AlertComponent, EmptyStateComponent],
  templateUrl: './context-upload-panel.component.html',
  styleUrl: './context-upload-panel.component.css'
})
export class ContextUploadPanelComponent implements OnDestroy {
  private readonly agentService = inject(AgentCoreService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly templates = input<readonly TemplateRead[]>([]);
  readonly templatesLoading = input(false);
  readonly templatesError = input('');

  readonly uploaded = output<void>();
  readonly errorOccurred = output<string>();

  readonly uploadMethod = signal<UploadMethod>('file');

  // File upload state
  readonly selectedFile = signal<File | null>(null);
  readonly uploadState = signal<UploadState>('idle');
  readonly uploadProgress = signal(0);
  readonly uploadMessage = signal('Selecciona un documento para cargar contexto real al agente.');
  readonly uploadError = signal('');
  private readonly allowedUploadExtensions = ['.txt', '.md', '.docx', '.pdf'];
  private readonly maxUploadBytes = 5 * 1024 * 1024;
  private uploadProgressTimer: ReturnType<typeof setInterval> | null = null;

  readonly fileForm = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(160)]]
  });

  readonly aiStartForm = this.fb.nonNullable.group({
    companyName: ['', [Validators.required, Validators.maxLength(120)]],
    industry: ['', [Validators.required, Validators.maxLength(120)]]
  });

  readonly aiMessageForm = this.fb.nonNullable.group({
    message: ['', [Validators.required, Validators.maxLength(2000)]]
  });

  readonly aiSessionId = signal('');
  readonly aiMessages = signal<AiChatMessage[]>([]);
  readonly aiLoading = signal(false);

  readonly uploadStatusLabel = computed(() => {
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
    return labels[this.uploadState()];
  });

  readonly shouldShowUploadProgress = computed(() =>
    ['validating', 'uploading', 'received', 'processing', 'success'].includes(this.uploadState())
  );

  ngOnDestroy(): void {
    this.stopUploadProgressFallback();
  }

  onFileSelected(event: Event): void {
    const inputEl = event.target as HTMLInputElement | null;
    const file = inputEl?.files?.[0] ?? null;
    if (file) {
      this.selectedFile.set(file);
      this.uploadState.set('selected');
      this.uploadProgress.set(0);
      this.uploadError.set('');
      this.uploadMessage.set(`Seleccionaste ${file.name} (${this.humanFileSize(file.size)}).`);
    } else {
      this.clearSelectedFile();
    }
  }

  clearSelectedFile(): void {
    if (this.uploadState() === 'uploading') return;
    this.stopUploadProgressFallback();
    this.selectedFile.set(null);
    this.uploadState.set('idle');
    this.uploadProgress.set(0);
    this.uploadError.set('');
    this.uploadMessage.set('Selecciona un documento para cargar contexto real al agente.');
  }

  submitFile(): void {
    this.stopUploadProgressFallback();
    this.uploadState.set('validating');
    this.uploadProgress.set(5);
    this.uploadMessage.set('Validando formato y tamaño antes de enviar al backend.');
    this.uploadError.set('');

    const file = this.selectedFile();
    const title = this.fileForm.controls.title.value.trim();
    if (!this.validateSelectedFile(file, title) || !file) return;

    this.uploadState.set('uploading');
    this.uploadProgress.set(12);
    this.uploadMessage.set('Enviando documento a flowkron-agent-core.');
    this.startUploadProgressFallback();

    this.agentService
      .uploadDocumentFileEvents(file, title, 'active', 100)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (event) => {
          if (event.type === HttpEventType.Sent) {
            this.uploadProgress.update((p) => Math.max(p, 15));
            return;
          }
          if (event.type === HttpEventType.UploadProgress) {
            this.uploadProgress.update((current) =>
              event.total ? Math.min(Math.max(Math.round((event.loaded / event.total) * 95), current), 95) : Math.max(current, 35)
            );
            return;
          }
          if (event.type === HttpEventType.Response) {
            this.stopUploadProgressFallback();
            this.uploadState.set('received');
            this.uploadProgress.set(100);
            this.uploadMessage.set('El backend recibió el documento y respondió correctamente.');
            if (event.body?.data) {
              this.uploadState.set('success');
              this.uploadMessage.set('Documento aceptado. Actualizando el estado real del contexto empresarial.');
              this.fileForm.reset({ title: '' });
              this.selectedFile.set(null);
              this.uploaded.emit();
            }
          }
        },
        error: (err: unknown) => {
          this.stopUploadProgressFallback();
          const msg = extractHttpErrorMessage(err, 'No pudimos procesar el documento. Intenta nuevamente.');
          this.setUploadError(msg);
          this.errorOccurred.emit(msg);
        }
      });
  }

  getDownloadOption(
    template: TemplateRead,
    format: 'docx' | 'pdf'
  ): TemplateRead['download_options'][number] | undefined {
    return (template.download_options ?? []).find((option) => option.format === format);
  }

  downloadTpl(id: number | undefined): void {
    if (!id) return;
    this.agentService
      .downloadTemplate(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ blob, filename }) => {
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          a.click();
          window.URL.revokeObjectURL(url);
        },
        error: () => this.errorOccurred.emit('Error al descargar la plantilla.')
      });
  }

  startAiSession(): void {
    if (this.aiStartForm.invalid || this.aiLoading()) return;
    const { companyName, industry } = this.aiStartForm.getRawValue();
    this.aiLoading.set(true);
    this.agentService
      .createSetupSession(companyName.trim(), industry.trim())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (session) => {
          this.aiSessionId.set(session.session_id);
          this.aiMessages.set([
            { id: '1', sender: 'bot', text: `¡Hola! Soy tu asistente de configuración de Flowkron para ${companyName.trim()}.` },
            { id: '2', sender: 'bot', text: session.next_question }
          ]);
          this.aiLoading.set(false);
        },
        error: () => {
          this.aiLoading.set(false);
          this.errorOccurred.emit('No se pudo iniciar la sesión de configuración con la IA.');
        }
      });
  }

  sendAiMessage(): void {
    if (this.aiMessageForm.invalid || this.aiLoading()) return;
    const userText = this.aiMessageForm.controls.message.value.trim();
    if (!userText) return;
    this.aiMessages.update((list) => [...list, { id: crypto.randomUUID(), sender: 'user', text: userText }]);
    this.aiMessageForm.reset({ message: '' });
    this.aiLoading.set(true);

    this.agentService
      .sendSetupMessage(this.aiSessionId(), userText)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.aiMessages.update((list) => [...list, { id: crypto.randomUUID(), sender: 'bot', text: res.next_question }]);
          this.aiLoading.set(false);
        },
        error: () => {
          this.aiMessages.update((list) => [
            ...list,
            { id: crypto.randomUUID(), sender: 'bot', text: 'Tuvimos un error conectando con la IA. ¿Puedes volver a intentar?' }
          ]);
          this.aiLoading.set(false);
        }
      });
  }

  generateAiContext(): void {
    if (this.aiLoading()) return;
    this.aiLoading.set(true);
    this.agentService
      .generateContext(this.aiSessionId())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.aiMessages.update((list) => [
            ...list,
            {
              id: crypto.randomUUID(),
              sender: 'bot',
              text: `He generado este resumen estructurado para revisión:\n${res.summary}\nCuando el backend entregue persistencia automática del asistente, se podrá incorporar al contexto empresarial.`
            }
          ]);
          this.aiLoading.set(false);
          this.uploaded.emit();
        },
        error: () => {
          this.aiLoading.set(false);
          this.errorOccurred.emit('Error al consolidar la información del asistente de IA.');
        }
      });
  }

  private validateSelectedFile(file: File | null, title: string): boolean {
    if (!file) {
      this.setUploadError('Selecciona un archivo antes de cargarlo.');
      return false;
    }
    if (!title) {
      this.setUploadError('Ingresa un título claro para identificar el documento.');
      return false;
    }
    const ext = file.name.toLowerCase().match(/\.[a-z0-9]+$/)?.[0] ?? '';
    if (!this.allowedUploadExtensions.includes(ext)) {
      this.setUploadError('El archivo no tiene un formato permitido. Usa PDF, Word, TXT o Markdown.');
      return false;
    }
    if (file.size <= 0) {
      this.setUploadError('El archivo está vacío. Selecciona un documento con contenido.');
      return false;
    }
    if (file.size > this.maxUploadBytes) {
      this.setUploadError(`El archivo supera el tamaño máximo permitido (${this.humanFileSize(this.maxUploadBytes)}).`);
      return false;
    }
    return true;
  }

  private humanFileSize(size: number): string {
    return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(Math.round(size / 1024), 1)} KB`;
  }

  private setUploadError(message: string): void {
    this.stopUploadProgressFallback();
    this.uploadState.set('error');
    this.uploadProgress.set(0);
    this.uploadError.set(message);
    this.uploadMessage.set('Corrige el problema y vuelve a intentarlo.');
  }

  private startUploadProgressFallback(): void {
    this.stopUploadProgressFallback();
    this.uploadProgressTimer = setInterval(() => {
      if (this.uploadState() !== 'uploading') {
        this.stopUploadProgressFallback();
        return;
      }
      this.uploadProgress.update((p) => (p < 90 ? Math.min(p + 7, 90) : p));
    }, 450);
  }

  private stopUploadProgressFallback(): void {
    if (this.uploadProgressTimer) {
      clearInterval(this.uploadProgressTimer);
      this.uploadProgressTimer = null;
    }
  }
}
