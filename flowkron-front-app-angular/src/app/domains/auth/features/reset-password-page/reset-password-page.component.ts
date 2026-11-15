import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

@Component({
  selector: 'flowkron-reset-password',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, AuthLayoutComponent],
  templateUrl: './reset-password-page.component.html',
  styleUrl: './reset-password-page.component.css'
})
export class ResetPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    token: ['', [Validators.required, Validators.pattern(/^\\d{3}-?\\d{3}$/)]],
    password: ['', Validators.required],
    confirmPassword: ['', Validators.required]
  });

  reset(): void {
    const { token, password, confirmPassword } = this.form.getRawValue();
    if (this.form.invalid || password !== confirmPassword) {
      this.form.markAllAsTouched();
      if (password !== confirmPassword) {
        this.errorMessage.set('Las contrasenas no coinciden.');
      }
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.auth.resetPassword(this.normalizeToken(token), password).subscribe({
      next: () => {
        this.successMessage.set('Contrasena actualizada. Ya puedes iniciar sesion.');
        setTimeout(() => void this.router.navigate(['/login']), 900);
      },
      error: (error: AuthError) => {
        this.errorMessage.set(error.message || 'No pudimos cambiar la contrasena.');
        this.isSubmitting.set(false);
      },
      complete: () => this.isSubmitting.set(false)
    });
  }

  private normalizeToken(token: string): string {
    const digits = token.replace(/\D/g, '');
    if (digits.length !== 6) {
      return token.trim();
    }
    return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  }
}
