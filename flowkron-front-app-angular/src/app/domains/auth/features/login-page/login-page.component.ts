import { Component, inject, signal } from '@angular/core';
import { LucideEye, LucideEyeOff } from '@lucide/angular';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { environment } from '@env/environment';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

@Component({
  selector: 'flowkron-login',
  standalone: true,
  imports: [ReactiveFormsModule, AuthLayoutComponent, LucideEye, LucideEyeOff],
  templateUrl: './login-page.component.html',
  styleUrl: './login-page.component.css'
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);

  readonly landingUrl = environment.landingUrl;
  showPassword = false;
  readonly mfaRequired = signal(false);
  readonly errorMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
    mfaCode: ['']
  });

  login(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    if (this.mfaRequired() && !value.mfaCode.trim()) {
      this.errorMessage.set('Ingresa el codigo MFA para continuar.');
      return;
    }

    this.errorMessage.set('');
    this.auth
      .login({
        email: value.email,
        password: value.password,
        mfa_code: value.mfaCode || undefined
      })
      .subscribe({
        next: (session) => void this.router.navigate([session.tenant ? '/app/home' : '/onboarding/company']),
        error: (error: AuthError) => {
          if (error.code === 'MFA_REQUIRED' || error.code?.endsWith('_MFA_REQUIRED')) {
            this.mfaRequired.set(true);
            this.errorMessage.set('Ingresa tu codigo MFA para completar el ingreso.');
            return;
          }
          if (error.code === 'AUTH_EMAIL_NOT_VERIFIED' || error.code?.endsWith('_AUTH_EMAIL_NOT_VERIFIED')) {
            this.errorMessage.set('Debes verificar tu correo antes de iniciar sesion.');
            return;
          }
          this.errorMessage.set(error.message || 'No pudimos iniciar sesion.');
        }
      });
  }

  goToForgotPassword(): void {
    void this.router.navigate(['/forgot-password']);
  }
}
