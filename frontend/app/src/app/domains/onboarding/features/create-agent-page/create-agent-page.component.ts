import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AgentsApiService } from '@domains/agents/data-access/agents-api.service';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

@Component({
  selector: 'kronflow-create-agent',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  templateUrl: './create-agent-page.component.html',
  styleUrl: './create-agent-page.component.css'
})
export class CreateAgentComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly operational = inject(AgentsApiService);
  private readonly auth = inject(AuthService);

  readonly isSaving = signal(false);
  readonly error = signal('');
  readonly runtimeCode = computed(() => this.auth.currentTenant()?.operational_runtime?.tenant_code || '');

  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    role: ['', Validators.required],
    tenantCode: ['', Validators.required]
  });

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    const expectedCode = this.runtimeCode();
    if (expectedCode && value.tenantCode.trim() !== expectedCode) {
      this.error.set('El codigo tenant no coincide con el tenant activo.');
      return;
    }

    this.isSaving.set(true);
    this.error.set('');
    this.operational
      .configureAgent({
        name: value.name,
        role: value.role,
        prompt_config: { tenant_code: value.tenantCode.trim() }
      })
      .subscribe({
        next: () => {
          this.isSaving.set(false);
          void this.router.navigate(['/app/home']);
        },
        error: () => {
          this.isSaving.set(false);
          this.error.set('No pudimos guardar el agente operacional.');
        }
      });
  }

  cancel(): void {
    void this.router.navigate(['/app/home']);
  }
}
