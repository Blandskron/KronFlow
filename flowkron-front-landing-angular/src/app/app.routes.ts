import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Flowkron · CRM inteligente para WhatsApp',
    loadComponent: () =>
      import('@domains/landing/features/landing-page/landing-page.component').then((m) => m.LandingComponent)
  },
  {
    path: 'politica-privacidad',
    title: 'Privacidad · Flowkron',
    loadComponent: () =>
      import('@domains/legal/features/privacy-policy/privacy-policy.component').then((m) => m.PrivacyPolicyComponent)
  },
  { path: '**', redirectTo: '' }
];