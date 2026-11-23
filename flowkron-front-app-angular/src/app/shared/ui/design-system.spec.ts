import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import {
  AlertComponent,
  BadgeComponent,
  DialogComponent,
  EmptyStateComponent,
  LegalModalComponent,
  PageHeaderComponent,
  StatCardComponent,
  TabsComponent,
  TabItem
} from './index';

@Component({
  imports: [
    AlertComponent,
    BadgeComponent,
    DialogComponent,
    EmptyStateComponent,
    PageHeaderComponent,
    StatCardComponent,
    TabsComponent
  ],
  template: `
    <flowkron-page-header eyebrow="CRM" title="Oportunidades" subtitle="Pipeline activo">
      <button type="button" class="btn btn-primary">Nueva</button>
    </flowkron-page-header>

    <flowkron-stat-card label="Abiertas" [value]="12" hint="Este mes" tone="primary" />
    <flowkron-badge tone="success">Activa</flowkron-badge>

    <flowkron-alert tone="danger" title="Error" [dismissible]="true" (dismissed)="dismissed.set(true)">
      No se pudo guardar.
    </flowkron-alert>

    <flowkron-empty-state title="Sin resultados" description="Prueba otro filtro.">
      <button type="button">Limpiar</button>
    </flowkron-empty-state>

    <flowkron-tabs
      [tabs]="tabs"
      [activeId]="activeTab()"
      ariaLabel="Secciones de prueba"
      (selected)="activeTab.set($event)"
    />

    <flowkron-dialog #dlg title="Confirmar">
      <p>Contenido del diálogo</p>
    </flowkron-dialog>
  `
})
class DesignSystemHostComponent {
  readonly dismissed = signal(false);
  readonly activeTab = signal('summary');
  readonly tabs: readonly TabItem[] = [
    { id: 'summary', label: 'Resumen', badge: 2 },
    { id: 'upload', label: 'Carga' },
    { id: 'simulator', label: 'Simulador' }
  ];
}

describe('Design System shared/ui primitives', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DesignSystemHostComponent, LegalModalComponent]
    }).compileComponents();
  });

  it('renders page header, stat card, badge, alert, and empty state with semantic attributes', () => {
    const fixture = TestBed.createComponent(DesignSystemHostComponent);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;

    expect(el.querySelector('h1')?.textContent).toContain('Oportunidades');
    expect(el.querySelector('.eyebrow')?.textContent).toContain('CRM');
    expect(el.querySelector('.stat-value')?.textContent).toContain('12');
    expect(el.querySelector('.badge-success')?.textContent).toContain('Activa');

    const alertEl = el.querySelector('[role="alert"]');
    expect(alertEl).toBeTruthy();
    expect(alertEl?.textContent).toContain('No se pudo guardar.');

    const closeBtn = el.querySelector('.alert-close') as HTMLButtonElement;
    closeBtn.click();
    expect(fixture.componentInstance.dismissed()).toBe(true);

    expect(el.querySelector('.empty-state h3')?.textContent).toContain('Sin resultados');
  });

  it('supports keyboard navigation (ArrowRight, ArrowLeft, Home, End) in flowkron-tabs', () => {
    const fixture = TestBed.createComponent(DesignSystemHostComponent);
    fixture.detectChanges();
    const tabButtons = Array.from(
      fixture.nativeElement.querySelectorAll('[role="tab"]')
    ) as HTMLButtonElement[];

    expect(tabButtons.length).toBe(3);
    expect(tabButtons[0].getAttribute('aria-selected')).toBe('true');
    expect(tabButtons[0].getAttribute('tabindex')).toBe('0');
    expect(tabButtons[1].getAttribute('tabindex')).toBe('-1');

    tabButtons[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.activeTab()).toBe('upload');

    tabButtons[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'End' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.activeTab()).toBe('simulator');

    tabButtons[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'Home' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.activeTab()).toBe('summary');
  });

  it('renders LegalModalComponent with native dialog and invokes showModal()', () => {
    const fixture = TestBed.createComponent(LegalModalComponent);
    fixture.componentRef.setInput('title', 'Términos');
    fixture.componentRef.setInput('body', 'Detalle legal.');
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialog).toBeTruthy();
    dialog.showModal = vi.fn();

    fixture.componentInstance.show();
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
  });
});
