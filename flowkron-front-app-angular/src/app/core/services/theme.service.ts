import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  readonly isDark = signal(true);

  initialize(): void {
    const savedTheme = localStorage.getItem('theme');
    this.setDark(savedTheme !== 'light');
  }

  toggle(): void {
    this.setDark(!this.isDark());
  }

  private setDark(isDark: boolean): void {
    this.isDark.set(isDark);
    this.document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }
}
