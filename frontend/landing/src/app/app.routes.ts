import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'KronFlow — Intelligent CRM',
    loadComponent: () =>
      import('@domains/landing/features/landing-page/landing-page.component').then((m) => m.LandingComponent)
  },
  {
    path: 'politica-privacidad',
    title: 'Privacidad · KronFlow',
    loadComponent: () =>
      import('@domains/legal/features/privacy-policy/privacy-policy.component').then((m) => m.PrivacyPolicyComponent)
  },
  { path: '**', redirectTo: '' }
];
