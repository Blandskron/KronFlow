import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('@domains/landing/features/landing-page/landing-page.component').then((m) => m.LandingComponent)
  },
  {
    path: 'politica-privacidad',
    loadComponent: () =>
      import('@domains/legal/features/privacy-policy/privacy-policy.component').then((m) => m.PrivacyPolicyComponent)
  },
  { path: '**', redirectTo: '' }
];