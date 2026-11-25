import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

const DARK_THEME_COLOR = '#060d10';
const LIGHT_THEME_COLOR = '#f1f8f7';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  readonly isDark = signal(true);

  initialize(): void {
    const savedTheme = this.readStoredTheme();
    this.setDark(savedTheme !== 'light');
  }

  toggle(): void {
    this.setDark(!this.isDark());
  }

  private setDark(isDark: boolean): void {
    this.isDark.set(isDark);
    this.document.documentElement.classList.toggle('dark', isDark);
    this.updateThemeColorMeta(isDark);
    this.writeStoredTheme(isDark ? 'dark' : 'light');
  }

  private updateThemeColorMeta(isDark: boolean): void {
    const meta = this.document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', isDark ? DARK_THEME_COLOR : LIGHT_THEME_COLOR);
    }
  }

  private readStoredTheme(): string | null {
    try {
      return localStorage.getItem('theme');
    } catch {
      return null;
    }
  }

  private writeStoredTheme(theme: 'dark' | 'light'): void {
    try {
      localStorage.setItem('theme', theme);
    } catch {
      // Ignora restricciones de storage (modo privado / cuota)
    }
  }
}
