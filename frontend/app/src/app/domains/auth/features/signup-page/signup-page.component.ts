import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

@Component({
  selector: 'kronflow-signup-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AuthLayoutComponent, ReactiveFormsModule, RouterLink],
  template: `
    <kronflow-auth-layout>
      <section class="auth-card">
        <a class="back" routerLink="/login">Volver a iniciar sesión</a>
        <h1>{{ token() ? 'Elige tu contraseña' : 'Crea tu cuenta de KronFlow' }}</h1>
        @if (completed()) {
          <p class="muted" role="status">Tu cuenta está lista. Inicia sesión para crear tu espacio de trabajo.</p>
          <a class="btn btn-primary" routerLink="/login">Iniciar sesión</a>
        } @else if (emailRequested() && !token()) {
          <p class="muted" role="status">
            Si la dirección está disponible, recibirás un enlace para verificarla y elegir tu contraseña.
          </p>
          <button class="btn btn-secondary" type="button" (click)="emailRequested.set(false)">Usar otro correo</button>
        } @else {
          <form (submit)="$event.preventDefault(); submit()" novalidate>
            @if (token()) {
              <p class="muted" id="password-hint">Usa al menos 12 caracteres y evita contraseñas comunes.</p>
              <label for="signup-password">Contraseña</label>
              <input class="field" id="signup-password" type="password" autocomplete="new-password" aria-describedby="password-hint" [formControl]="password">
              <label for="signup-password-confirm">Confirmar contraseña</label>
              <input class="field" id="signup-password-confirm" type="password" autocomplete="new-password" [formControl]="confirmation">
            } @else {
              <p class="muted">Te enviaremos un enlace para confirmar tu correo.</p>
              <label for="signup-email">Correo electrónico</label>
              <input class="field" id="signup-email" type="email" autocomplete="email" [formControl]="email">
            }
            @if (error()) {
              <p class="error" role="alert">{{ error() }}</p>
            }
            <button class="btn btn-primary" type="submit" [disabled]="busy()">
              {{ busy() ? 'Procesando…' : token() ? 'Crear cuenta' : 'Enviar enlace' }}
            </button>
          </form>
        }
      </section>
    </kronflow-auth-layout>
  `,
  styles: `
    h1 { margin: 16px 0 8px; }
    form { display: grid; gap: 12px; }
    .back { color: var(--primary); font-weight: 700; }
    .error { margin: 0; color: var(--error-text); }
  `
})
export class SignupPageComponent {
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);

  private readonly fragment = toSignal(inject(ActivatedRoute).fragment);
  readonly token = computed(() => new URLSearchParams(this.fragment() ?? '').get('token'));
  readonly email = this.fb.nonNullable.control('', [Validators.required, Validators.email, Validators.maxLength(150)]);
  readonly password = this.fb.nonNullable.control('', [Validators.required, Validators.minLength(12), Validators.maxLength(128)]);
  readonly confirmation = this.fb.nonNullable.control('');
  readonly busy = signal(false);
  readonly completed = signal(false);
  readonly emailRequested = signal(false);
  readonly error = signal('');

  submit(): void {
    if (this.busy()) {
      return;
    }
    this.error.set('');
    const token = this.token();
    if (token && (this.password.invalid || this.password.value !== this.confirmation.value)) {
      this.error.set('Ingresa una contraseña de entre 12 y 128 caracteres y confirma que coincida.');
      return;
    }
    if (!token && this.email.invalid) {
      this.error.set('Ingresa un correo electrónico válido.');
      return;
    }

    this.busy.set(true);
    const request = token
      ? this.auth.completeSignup(token, this.password.value)
      : this.auth.requestSignup(this.email.value);

    request.pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.busy.set(false))).subscribe({
      next: () => {
        if (token) {
          this.password.reset();
          this.confirmation.reset();
          this.completed.set(true);
        } else {
          this.emailRequested.set(true);
        }
      },
      error: (error: AuthError) => this.error.set(error.message)
    });
  }
}
