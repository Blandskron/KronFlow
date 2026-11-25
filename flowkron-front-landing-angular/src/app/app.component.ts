import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ThemeService } from './core/services/theme.service';

@Component({
  selector: 'kronflow-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet],
  template: '<router-outlet />'
})
export class AppComponent {
  private readonly themeService = inject(ThemeService);

  constructor() {
    this.themeService.initialize();
  }
}
