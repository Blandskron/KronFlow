import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, output, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { LucideInfo, LucideMessageSquare, LucideSend } from '@lucide/angular';
import { AgentCoreService } from '@domains/agents/data-access';
import { AgentActionItem, AgentSource } from '@domains/agents/domain';
import { BadgeComponent, DialogComponent, EmptyStateComponent } from '@shared/ui';

export interface SimulatorMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  confidence?: number;
  requiresHuman?: boolean;
  sources?: AgentSource[];
  actions?: AgentActionItem[];
}

@Component({
  selector: 'kronflow-agent-simulator-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe,
    ReactiveFormsModule,
    LucideInfo,
    LucideMessageSquare,
    LucideSend,
    BadgeComponent,
    DialogComponent,
    EmptyStateComponent
  ],
  templateUrl: './agent-simulator-panel.component.html',
  styleUrl: './agent-simulator-panel.component.css'
})
export class AgentSimulatorPanelComponent {
  private readonly agentService = inject(AgentCoreService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly hasDraftDocuments = input(false);
  readonly publishDrafts = output<void>();
  readonly errorOccurred = output<string>();

  private readonly correctionDialog = viewChild.required<DialogComponent>('correctionDialog');

  readonly simMessages = signal<SimulatorMessage[]>([]);
  readonly simLoading = signal(false);
  readonly selectedMessage = signal<SimulatorMessage | null>(null);

  readonly simForm = this.fb.nonNullable.group({
    prompt: ['', [Validators.required, Validators.maxLength(2000)]]
  });

  readonly ruleForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(160)]],
    content: ['', [Validators.required, Validators.maxLength(2000)]]
  });

  sendSimMessage(): void {
    if (this.simForm.invalid || this.simLoading()) return;
    const text = this.simForm.controls.prompt.value.trim();
    if (!text) return;

    this.simMessages.update((list) => [...list, { id: crypto.randomUUID(), sender: 'user', text }]);
    this.simForm.reset({ prompt: '' });
    this.simLoading.set(true);

    this.agentService
      .simulate({
        channel: 'webchat',
        conversation_id: 'sim-session-1',
        customer: { external_id: 'sim-user' },
        message: { type: 'text', content: text, attachments: [] },
        metadata: { raw_payload: {} }
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const botMsg: SimulatorMessage = {
            id: crypto.randomUUID(),
            sender: 'bot',
            text: res.reply.content,
            confidence: res.confidence,
            requiresHuman: res.requires_human,
            sources: res.sources,
            actions: res.actions
          };
          this.simMessages.update((list) => [...list, botMsg]);
          this.selectedMessage.set(botMsg);
          this.simLoading.set(false);
        },
        error: () => {
          this.simMessages.update((list) => [
            ...list,
            {
              id: crypto.randomUUID(),
              sender: 'bot',
              text: 'Error de simulación. El core no respondió de forma correcta. Revisa la conectividad en el puerto 8002.'
            }
          ]);
          this.simLoading.set(false);
        }
      });
  }

  selectMessage(msg: SimulatorMessage): void {
    if (msg.sender === 'bot') {
      this.selectedMessage.set(msg);
    }
  }

  openCorrectionModal(): void {
    if (!this.selectedMessage()) return;
    const msgs = this.simMessages();
    const lastUserPrompt = msgs[msgs.length - 2]?.text || 'pregunta';
    this.ruleForm.setValue({
      name: `Corrección para: "${lastUserPrompt}"`,
      content: ''
    });
    this.correctionDialog().open();
  }

  saveCorrection(): void {
    if (this.ruleForm.invalid) return;
    const { name, content } = this.ruleForm.getRawValue();
    this.agentService
      .createRule({
        name: name.trim(),
        rule_type: 'correction',
        content: content.trim(),
        priority: 10,
        is_active: true
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.ruleForm.reset({ name: '', content: '' });
          this.correctionDialog().close();
        },
        error: () => this.errorOccurred.emit('Error al crear la regla. Verifica la persistencia en el core.')
      });
  }
}
