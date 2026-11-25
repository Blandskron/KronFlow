import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideBookOpen, LucideLink, LucideMessageSquare, LucideSettings } from '@lucide/angular';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

@Component({
  selector: 'kronflow-home-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, LucideLink, LucideMessageSquare, LucideBookOpen, LucideSettings],
  templateUrl: './home-page.component.html',
  styleUrl: './home-page.component.css'
})
export class HomePageComponent {
  private readonly auth = inject(AuthService);

  readonly displayName = computed(() => this.auth.displayName());
  readonly tenantName = computed(() => this.auth.currentTenant()?.name || 'Tu empresa');
}
