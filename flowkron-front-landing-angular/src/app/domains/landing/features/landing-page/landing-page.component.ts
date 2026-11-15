import { Component, inject } from '@angular/core';
import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { RouterLink } from '@angular/router';
import {
  LucideArrowRight,
  LucideMessageSquare
} from '@lucide/angular';
import { ContactPayload, ContactService } from '@domains/landing/data-access/contact.service';
import { LegalModalComponent } from '@shared/ui/legal-modal.component';
import { ThemeToggleComponent } from '@shared/ui/theme-toggle.component';
import { environment } from '@env/environment';

type ContactStatus = 'idle' | 'success' | 'error';
type ContactControlName = 'name' | 'email' | 'company' | 'phone' | 'message' | 'acceptTerms';

const htmlTagPattern = /<[^>]*>/;
const controlCharsPattern = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/;
const sqlControlPattern = /(--|\/\*|\*\/|;|\bunion\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\balter\b)/i;
const phonePattern = /^[0-9+()\-\s]{0,32}$/;

function safeTextValidator(control: AbstractControl): ValidationErrors | null {
  const value = String(control.value ?? '');
  if (!value) {
    return null;
  }
  if (controlCharsPattern.test(value) || htmlTagPattern.test(value) || sqlControlPattern.test(value)) {
    return { unsafeText: true };
  }
  return null;
}

@Component({
  selector: 'flowkron-landing',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    ThemeToggleComponent,
    LegalModalComponent,
    LucideArrowRight,
    LucideMessageSquare
  ],
  templateUrl: './landing-page.component.html',
  styleUrl: './landing-page.component.css'
})
export class LandingComponent {
  private readonly fb = inject(FormBuilder);
  private readonly contactService = inject(ContactService);

  readonly loginUrl = `${environment.appUrl}/login`;

  showTerms = false;
  submitting = false;
  contactStatus: ContactStatus = 'idle';

  readonly contactForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120), safeTextValidator]],
    email: ['', [Validators.required, Validators.email, Validators.maxLength(254)]],
    company: ['', [Validators.maxLength(120), safeTextValidator]],
    phone: ['', [Validators.maxLength(32), Validators.pattern(phonePattern), safeTextValidator]],
    message: ['', [Validators.required, Validators.maxLength(2000), safeTextValidator]],
    acceptTerms: [false, Validators.requiredTrue]
  });

  readonly salesWhatsAppNumber = environment.salesWhatsAppNumber;

  openWhatsApp(): void {
    const message = encodeURIComponent('Hola, me interesa conocer mas sobre Flowkron');
    window.open(`https://wa.me/${this.salesWhatsAppNumber}?text=${message}`, '_blank', 'noopener');
  }

  submitContact(): void {
    if (this.contactForm.invalid) {
      this.contactForm.markAllAsTouched();
      return;
    }

    const payload: ContactPayload = {
      name: this.contactForm.controls.name.value.trim(),
      email: this.contactForm.controls.email.value.trim().toLowerCase(),
      company: this.contactForm.controls.company.value.trim(),
      phone: this.contactForm.controls.phone.value.trim(),
      message: this.contactForm.controls.message.value.trim(),
      accept_terms: this.contactForm.controls.acceptTerms.value
    };

    this.submitting = true;
    this.contactStatus = 'idle';

    this.contactService
      .send(payload)
      .pipe(finalize(() => (this.submitting = false)))
      .subscribe({
        next: () => {
          this.contactStatus = 'success';
          this.contactForm.reset({
            name: '',
            email: '',
            company: '',
            phone: '',
            message: '',
            acceptTerms: false
          });
        },
        error: () => {
          this.contactStatus = 'error';
        }
      });
  }

  isInvalid(controlName: ContactControlName): boolean {
    const control = this.contactForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }
}
