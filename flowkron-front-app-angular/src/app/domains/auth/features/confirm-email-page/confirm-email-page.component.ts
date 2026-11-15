import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthError } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { AuthLayoutComponent } from '../auth-layout/auth-layout.component';

type ConfirmationState = 'idle' | 'submitting' | 'success' | 'error';

@Component({
  selector: 'flowkron-confirm-email',
  standalone: true,
  imports: [RouterLink, AuthLayoutComponent],
  templateUrl: './confirm-email-page.component.html',
  styleUrl: './confirm-email-page.component.css'
})
export class ConfirmEmailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(AuthService);

  readonly token = signal(this.route.snapshot.queryParamMap.get('token') || '');
  readonly state = signal<ConfirmationState>(this.token() ? 'idle' : 'error');
  readonly errorMessage = signal(this.token() ? '' : 'El enlace de confirmacion no incluye un token valido.');

  readonly isSubmitting = computed(() => this.state() === 'submitting');
  readonly isSuccess = computed(() => this.state() === 'success');

  confirm(): void {
    const token = this.token().trim();
    if (!token || this.isSubmitting() || this.isSuccess()) {
      return;
    }

    this.state.set('submitting');
    this.errorMessage.set('');
    this.auth.confirmEmail(token).subscribe({
      next: () => this.state.set('success'),
      error: (error: AuthError) => {
        this.state.set('error');
        this.errorMessage.set(error.message || 'No pudimos confirmar el correo.');
      }
    });
  }
}
