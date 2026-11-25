import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { LegalModalComponent } from './legal-modal.component';

describe('LegalModalComponent (landing)', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LegalModalComponent]
    }).compileComponents();
  });

  it('renders title and body inside a native dialog element', () => {
    const fixture = TestBed.createComponent(LegalModalComponent);
    fixture.componentRef.setInput('title', 'Términos de uso');
    fixture.componentRef.setInput('body', 'Condiciones de ejemplo.');
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute('aria-labelledby')).toBe('legal-title');
    expect(dialog.textContent).toContain('Términos de uso');
    expect(dialog.textContent).toContain('Condiciones de ejemplo.');
  });

  it('invokes showModal on the native dialog when show() is called', () => {
    const fixture = TestBed.createComponent(LegalModalComponent);
    fixture.componentRef.setInput('title', 'Términos');
    fixture.componentRef.setInput('body', 'Texto');
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    dialog.showModal = vi.fn();

    fixture.componentInstance.show();
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
  });
});
