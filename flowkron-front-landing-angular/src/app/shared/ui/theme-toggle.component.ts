import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideMoon, LucideSun } from '@lucide/angular';
import { ThemeService } from '@core/services/theme.service';

@Component({
  selector: 'flowkron-theme-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LucideMoon, LucideSun],
  template: `
    <button class="icon-btn" type="button" [attr.aria-label]="label()" (click)="theme.toggle()">
      @if (theme.isDark()) {
        <svg lucideSun size="18"></svg>
      } @else {
        <svg lucideMoon size="18"></svg>
      }
    </button>
  `
})
export class ThemeToggleComponent {
  readonly theme = inject(ThemeService);

  label(): string {
    return this.theme.isDark() ? 'Activar modo claro' : 'Activar modo oscuro';
  }
}
