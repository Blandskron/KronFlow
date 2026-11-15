import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideBot, LucideCheckCircle2 } from '@lucide/angular';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

@Component({
  selector: 'flowkron-home-page',
  standalone: true,
  imports: [RouterLink, LucideBot, LucideCheckCircle2],
  templateUrl: './home-page.component.html',
  styleUrl: './home-page.component.css'
})
export class HomePageComponent {
  private readonly auth = inject(AuthService);

  readonly requiresPlan = computed(() => Boolean(this.auth.subscription()?.requires_paid_plan));
  readonly displayName = computed(() => this.auth.displayName());
  readonly tenantName = computed(() => this.auth.currentTenant()?.name || 'Tu empresa');
}
