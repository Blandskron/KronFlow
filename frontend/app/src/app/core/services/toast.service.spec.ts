import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let service: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({});
    service = TestBed.inject(ToastService);
    service.clear();
  });

  afterEach(() => {
    service.clear();
    vi.useRealTimers();
  });

  it('adds and auto-dismisses toast messages', () => {
    service.success('Guardado correctamente', 2000);
    expect(service.items().length).toBe(1);
    expect(service.items()[0].tone).toBe('success');

    vi.advanceTimersByTime(2000);
    expect(service.items().length).toBe(0);
  });

  it('caps visible stack to at most 4 items and supports manual dismiss', () => {
    const id1 = service.info('Uno', 0);
    service.info('Dos', 0);
    service.info('Tres', 0);
    service.info('Cuatro', 0);
    const id5 = service.error('Cinco', 0);

    expect(service.items().length).toBe(4);
    expect(service.items().some((t) => t.id === id1)).toBe(false);
    expect(service.items().some((t) => t.id === id5)).toBe(true);

    service.dismiss(id5);
    expect(service.items().length).toBe(3);
  });
});
