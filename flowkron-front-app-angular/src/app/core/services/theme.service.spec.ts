import { DOCUMENT } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  let service: ThemeService;
  let doc: Document;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    service = TestBed.inject(ThemeService);
    doc = TestBed.inject(DOCUMENT);
    doc.documentElement.classList.remove('dark');
  });

  it('defaults to dark theme when no preference is stored', () => {
    service.initialize();

    expect(service.isDark()).toBe(true);
    expect(doc.documentElement.classList.contains('dark')).toBe(true);
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('respects stored light theme preference', () => {
    localStorage.setItem('theme', 'light');
    service.initialize();

    expect(service.isDark()).toBe(false);
    expect(doc.documentElement.classList.contains('dark')).toBe(false);
  });

  it('toggles between dark and light themes', () => {
    service.initialize();
    service.toggle();

    expect(service.isDark()).toBe(false);
    expect(doc.documentElement.classList.contains('dark')).toBe(false);
    expect(localStorage.getItem('theme')).toBe('light');

    service.toggle();
    expect(service.isDark()).toBe(true);
    expect(doc.documentElement.classList.contains('dark')).toBe(true);
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('synchronizes meta[name="theme-color"] when present', () => {
    const meta = doc.createElement('meta');
    meta.setAttribute('name', 'theme-color');
    doc.head.appendChild(meta);

    service.initialize();
    expect(meta.getAttribute('content')).toBe('#100d16');

    service.toggle();
    expect(meta.getAttribute('content')).toBe('#f8f6fb');
    meta.remove();
  });
});
