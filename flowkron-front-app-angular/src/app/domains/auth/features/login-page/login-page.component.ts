import { AfterViewInit, Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { LucideEye, LucideEyeOff } from '@lucide/angular';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthError, GoogleLoginRequest, MeResponse } from '@domains/auth/domain/auth.model';
import { loadGoogleIdentity } from '@domains/auth/data-access/google-identity';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { environment } from '@env/environment';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

@Component({
  selector: 'flowkron-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, AuthLayoutComponent, LucideEye, LucideEyeOff],
  templateUrl: './login-page.component.html',
  styleUrl: './login-page.component.css'
})
export class LoginComponent implements AfterViewInit {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly googleButton = viewChild.required<ElementRef<HTMLDivElement>>('googleButton');
  private googleChallenge: GoogleLoginRequest | null = null;
  readonly signupEnabled = signal(true);
  readonly googleMfa = signal(false);
  readonly googleError = signal('');
  readonly googleCode = this.fb.nonNullable.control('', [Validators.required, Validators.pattern('^[0-9]{6}$')]);

  readonly landingUrl = environment.landingUrl;
  showPassword = false;
  readonly mfaRequired = signal(false);
  readonly errorMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
    mfaCode: ['']
  });

  ngAfterViewInit(): void {
    this.loadAuthOptions();
  }

  private loadAuthOptions(): void {
    this.auth.authOptions().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: async (options) => {
        this.signupEnabled.set(options.signup_enabled);
        if (!options.google_client_id) {
          return;
        }

        try {
          const google = await loadGoogleIdentity();
          if (this.destroyRef.destroyed) {
            return;
          }
          const host = this.googleButton().nativeElement;
          host.replaceChildren();
          google.initialize({
            client_id: options.google_client_id,
            nonce: options.google_nonce,
            auto_select: false,
            callback: ({ credential }) => {
              if (!this.destroyRef.destroyed) {
                this.submitGoogle({ credential, nonce: options.google_nonce });
              }
            }
          });
          google.renderButton(host, {
            type: 'standard', theme: 'outline', size: 'large', text: 'continue_with',
            locale: 'es', width: Math.min(360, host.parentElement?.clientWidth || 240)
          });
        } catch {
          if (!this.destroyRef.destroyed) {
            this.googleError.set('No pudimos cargar el botón de Google. Puedes iniciar sesión con tu contraseña.');
          }
        }
      },
      error: () => undefined
    });
  }

  confirmGoogleMfa(): void {
    if (this.googleChallenge && this.googleCode.valid) {
      this.submitGoogle({ ...this.googleChallenge, mfa_code: this.googleCode.value });
    }
  }

  cancelGoogleMfa(): void {
    this.googleChallenge = null;
    this.googleMfa.set(false);
    this.googleCode.reset();
    this.googleError.set('');
  }

  private submitGoogle(request: GoogleLoginRequest): void {
    if (this.auth.isLoading()) {
      return;
    }
    this.googleError.set('');
    this.auth.googleLogin(request).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (session) => this.openWorkspace(session),
      error: (error: AuthError) => {
        if (error.code === 'MFA_REQUIRED' || error.code?.endsWith('_MFA_REQUIRED')) {
          this.googleChallenge = request;
          this.googleMfa.set(true);
          this.googleCode.reset();
        } else {
          this.cancelGoogleMfa();
          this.loadAuthOptions();
        }
        this.googleError.set(error.message);
      }
    });
  }

  private openWorkspace(session: MeResponse): void {
    void this.router.navigate([session.tenant ? '/app/home' : '/onboarding/company']);
  }

  login(): void {
    if (this.auth.isLoading()) {
      return;
    }

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.errorMessage.set('Ingresa un correo electrónico válido y tu contraseña.');
      return;
    }

    const value = this.form.getRawValue();
    if (this.mfaRequired() && !value.mfaCode.trim()) {
      this.errorMessage.set('Ingresa el código MFA para continuar.');
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
        next: (session) => this.openWorkspace(session),
        error: (error: AuthError) => {
          if (error.code === 'MFA_REQUIRED' || error.code?.endsWith('_MFA_REQUIRED')) {
            this.mfaRequired.set(true);
            this.errorMessage.set('Ingresa tu código MFA para completar el ingreso.');
            return;
          }
          if (error.code === 'AUTH_EMAIL_NOT_VERIFIED' || error.code?.endsWith('_AUTH_EMAIL_NOT_VERIFIED')) {
            this.errorMessage.set('Debes verificar tu correo antes de iniciar sesión.');
            return;
          }
          this.errorMessage.set(error.message || 'No pudimos iniciar sesión.');
        }
      });
  }

  goToForgotPassword(): void {
    void this.router.navigate(['/forgot-password']);
  }
}
