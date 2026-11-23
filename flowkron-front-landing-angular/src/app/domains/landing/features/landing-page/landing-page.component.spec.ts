import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ContactService } from '@domains/landing/data-access/contact.service';
import { LandingComponent } from './landing-page.component';

describe('LandingComponent', () => {
  let contactStub: { send: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    contactStub = {
      send: vi.fn(() => of({ id: 1, created_at: '2026-11-23T00:00:00Z' }))
    };

    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideRouter([]), { provide: ContactService, useValue: contactStub }]
    }).compileComponents();
  });

  it('renders the hero heading and rejects invalid contact submissions', () => {
    const fixture = TestBed.createComponent(LandingComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('CRM inteligente');

    fixture.componentInstance.submitContact();
    expect(contactStub.send).not.toHaveBeenCalled();
    expect(fixture.componentInstance.isInvalid('name')).toBe(true);
    expect(fixture.componentInstance.isInvalid('email')).toBe(true);
    expect(fixture.componentInstance.isInvalid('acceptTerms')).toBe(true);
  });

  it('rejects unsafe HTML or SQL patterns in text fields', () => {
    const fixture = TestBed.createComponent(LandingComponent);
    const form = fixture.componentInstance.contactForm;

    form.controls.name.setValue('<script>alert(1)</script>');
    expect(form.controls.name.errors).toEqual({ unsafeText: true });

    form.controls.message.setValue('SELECT * FROM users; --');
    expect(form.controls.message.errors).toEqual({ unsafeText: true });
  });

  it('submits valid contact form, sets success status, and resets fields', () => {
    const fixture = TestBed.createComponent(LandingComponent);
    const comp = fixture.componentInstance;

    comp.contactForm.setValue({
      name: '  Grace Hopper  ',
      email: 'GRACE@EXAMPLE.COM',
      company: 'Flowkron',
      phone: '+56 9 1111 2222',
      message: 'Consulta de prueba',
      acceptTerms: true
    });

    comp.submitContact();

    expect(contactStub.send).toHaveBeenCalledWith({
      name: 'Grace Hopper',
      email: 'grace@example.com',
      company: 'Flowkron',
      phone: '+56 9 1111 2222',
      message: 'Consulta de prueba',
      accept_terms: true
    });
    expect(comp.contactStatus()).toBe('success');
    expect(comp.contactForm.controls.name.value).toBe('');
    expect(comp.contactForm.controls.acceptTerms.value).toBe(false);
  });

  it('sets error status when submission fails', () => {
    contactStub.send.mockReturnValueOnce(throwError(() => new Error('network')));

    const fixture = TestBed.createComponent(LandingComponent);
    const comp = fixture.componentInstance;
    comp.contactForm.setValue({
      name: 'Alan Turing',
      email: 'alan@example.com',
      company: '',
      phone: '',
      message: 'Hola',
      acceptTerms: true
    });

    comp.submitContact();
    expect(comp.contactStatus()).toBe('error');
  });
});
