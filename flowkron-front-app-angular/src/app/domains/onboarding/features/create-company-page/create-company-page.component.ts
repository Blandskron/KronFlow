import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { WorkspaceStateService } from '@core/services/workspace-state.service';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuthLayoutComponent } from '@domains/auth/features/auth-layout/auth-layout.component';

@Component({
  selector: 'flowkron-create-company-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, AuthLayoutComponent],
  templateUrl: './create-company-page.component.html',
  styleUrl: './create-company-page.component.css'
})
export class CreateCompanyPageComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly workspace = inject(WorkspaceStateService);
  readonly auth = inject(AuthService);

  readonly errorMessage = signal('');
  readonly loggingOut = signal(false);

  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    legal_name: [''],
    tax_id: [''],
    country: ['CL', [Validators.required, Validators.minLength(2), Validators.maxLength(2)]]
  });

  createCompany(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    this.errorMessage.set('');
    this.auth
      .completeTenantOnboarding({
        name: value.name.trim(),
        legal_name: value.legal_name.trim() || undefined,
        tax_id: value.tax_id.trim() || undefined,
        country: value.country.trim().toUpperCase()
      })
      .subscribe({
        next: () => void this.router.navigate(['/app/home']),
        error: (error: AuthError) => this.errorMessage.set(error.message || 'No pudimos crear la empresa.')
      });
  }

  logout(): void {
    if (this.loggingOut() || this.auth.isLoading()) {
      return;
    }

    this.loggingOut.set(true);
    this.workspace.logout();
    this.auth.logout().subscribe(() => void this.router.navigate(['/login']));
  }
}
