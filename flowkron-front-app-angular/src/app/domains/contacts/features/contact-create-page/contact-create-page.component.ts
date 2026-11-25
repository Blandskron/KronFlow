import { Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ContactDraft, ContactsApiService } from '@domains/contacts/data-access/contacts-api.service';
import { finalize } from 'rxjs';

@Component({
  selector: 'kronflow-contact-create-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="page-section">
      <a class="btn btn-secondary" routerLink="/app/contacts" queryParamsHandling="preserve" [state]="backState">Volver a Contactos</a>
      <h1>Nuevo contacto</h1>
      @if (auth.hasPermission('crm.manage')) {
        <form class="card" (submit)="$event.preventDefault(); create(name.value, email.value, phone.value)">
          <label>Nombre
            <input #name class="field" name="name" autocomplete="name" required maxlength="180" [readonly]="locked()" />
          </label>
          <label>Correo electrónico (opcional)
            <input #email class="field" name="email" autocomplete="email" type="email" maxlength="254" [readonly]="locked()" />
          </label>
          <label>Teléfono (opcional)
            <input #phone class="field" name="phone" autocomplete="tel" type="tel" maxlength="80"
              placeholder="+56 9 1234 5678" [readonly]="locked()" />
          </label>
          <button class="btn btn-primary" type="submit" [disabled]="saving()">{{ pending() && !saving() ? 'Reintentar alta' : 'Crear contacto' }}</button>
          @if (error()) { <p role="alert">{{ error() }}</p> }
        </form>
      } @else { <p role="alert">No tienes permiso para crear contactos en esta empresa.</p> }
    </section>
  `,
  styles: `
    .page-section { padding: clamp(18px, 3vw, 32px); }
    form { display: grid; max-width: 36rem; gap: 12px; }
    label { display: grid; gap: 4px; }
    button { justify-self: start; }
  `
})
export class ContactCreatePageComponent {
  private readonly contacts = inject(ContactsApiService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requestId = crypto.randomUUID();
  private readonly previousState = inject(Location).getState() as { contactSearch?: unknown } | null;

  readonly auth = inject(AuthService);
  readonly backState = { contactSearch: this.previousState?.contactSearch };
  readonly saving = signal(false);
  readonly pending = signal<ContactDraft | null>(null);
  readonly error = signal('');

  locked(): boolean { return this.saving() || this.pending() !== null; }

  create(name: string, email: string, phone: string): void {
    if (this.saving()) return;
    const draft = this.pending() ?? {
      request_id: this.requestId, full_name: name.trim(), email: email.trim() || null, phone: phone.trim() || null
    };
    if (!draft.full_name) {
      this.error.set('Ingresa el nombre del contacto.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.contacts.create(draft).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))
    ).subscribe({
      next: ({ contact }) => { void this.router.navigate(['/app/contacts', contact.id], { queryParamsHandling: 'preserve', state: this.backState }); },
      error: (error: HttpErrorResponse) => {
        if (error.status === 422) {
          this.pending.set(null);
          this.error.set('Revisa los datos. El teléfono requiere un prefijo internacional como +56.');
        } else if (error.status === 403) {
          this.error.set('No tienes permiso para crear contactos en esta empresa.');
        } else {
          this.pending.set(draft);
          this.error.set('No pudimos confirmar el alta. Reintenta el mismo envío.');
        }
      }
    });
  }
}
