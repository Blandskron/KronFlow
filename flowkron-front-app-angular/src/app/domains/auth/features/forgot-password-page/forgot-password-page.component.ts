import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

@Component({
  selector: 'kronflow-forgot-password',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, AuthLayoutComponent],
  templateUrl: './forgot-password-page.component.html',
  styleUrl: './forgot-password-page.component.css'
})
export class ForgotPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]]
  });

  sendCode(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const email = this.form.getRawValue().email;
    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.auth.requestPasswordReset(email).subscribe({
      next: () => {
        this.successMessage.set('Si el correo existe, enviaremos un codigo de recuperacion.');
        setTimeout(() => void this.router.navigate(['/reset-password'], { queryParams: { email } }), 700);
      },
      error: (error: AuthError) => {
        this.errorMessage.set(error.message || 'No pudimos enviar el codigo.');
        this.isSubmitting.set(false);
      },
      complete: () => this.isSubmitting.set(false)
    });
  }
}
