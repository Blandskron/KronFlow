import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { environment } from '@env/environment';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

@Component({
  selector: 'flowkron-pricing-page',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './pricing-page.component.html',
  styleUrl: './pricing-page.component.css'
})
export class PricingPageComponent {
  private readonly auth = inject(AuthService);

  readonly subscription = this.auth.subscription;
  readonly currentPlanLabel = computed(() => {
    const plan = this.subscription()?.plan;
    const labels: Record<string, string> = {
      free: 'Base',
      starter: 'Standard',
      pro: 'Advanced',
      enterprise: 'Corporate'
    };
    return plan ? labels[plan] || plan : 'Sin plan asignado';
  });
  readonly contactUrl = environment.salesWhatsAppNumber
    ? `https://wa.me/${environment.salesWhatsAppNumber}?text=${encodeURIComponent('Hola, necesito configurar el acceso a mi espacio de Flowkron.')}`
    : `${environment.landingUrl}/#contact`;
}
