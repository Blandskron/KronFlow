import { Routes } from '@angular/router';
import { authGuard } from '@core/guards/auth.guard';
import { noAuthGuard } from '@core/guards/no-auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    canActivate: [noAuthGuard],
    loadComponent: () => import('@domains/auth/features/login-page/login-page.component').then((m) => m.LoginComponent)
  },
  {
    path: 'forgot-password',
    loadComponent: () =>
      import('@domains/auth/features/forgot-password-page/forgot-password-page.component').then((m) => m.ForgotPasswordComponent)
  },
  {
    path: 'confirm-email',
    loadComponent: () =>
      import('@domains/auth/features/confirm-email-page/confirm-email-page.component').then((m) => m.ConfirmEmailComponent)
  },
  {
    path: 'reset-password',
    loadComponent: () =>
      import('@domains/auth/features/reset-password-page/reset-password-page.component').then((m) => m.ResetPasswordComponent)
  },
  {
    path: 'onboarding/company',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@domains/onboarding/features/create-company-page/create-company-page.component').then(
        (m) => m.CreateCompanyPageComponent
      )
  },
  {
    path: 'app',
    canActivate: [authGuard],
    canActivateChild: [authGuard],
    loadComponent: () =>
      import('@domains/dashboard/features/dashboard-shell/dashboard-shell.component').then(
        (m) => m.DashboardShellComponent
      ),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'home' },
      {
        path: 'home',
        loadComponent: () =>
          import('@domains/dashboard/features/home-page/home-page.component').then((m) => m.HomePageComponent)
      },
      {
        path: 'business-context',
        loadComponent: () =>
          import('@domains/agents/features/business-context-page/business-context-page.component').then(
            (m) => m.BusinessContextPageComponent
          )
      },

      {
        path: 'conversations',
        loadComponent: () =>
          import('@domains/conversations/features/chats-page/chats-page.component').then((m) => m.ChatsPageComponent)
      },
      {
        path: 'workflows',
        loadComponent: () =>
          import('@domains/leads/features/workflows-page/workflows-page.component').then(
            (m) => m.WorkflowsPageComponent
          )
      },
      {
        path: 'integrations',
        loadComponent: () =>
          import('@domains/dashboard/features/placeholder-page/placeholder-page.component').then(
            (m) => m.PlaceholderPageComponent
          ),
        data: { title: 'Integraciones', description: 'Seccion en desarrollo...' }
      },
      {
        path: 'analytics',
        loadComponent: () =>
          import('@domains/analytics/features/analytics-page/analytics-page.component').then(
            (m) => m.AnalyticsPageComponent
          )
      },
      {
        path: 'notifications',
        loadComponent: () =>
          import('@domains/dashboard/features/notifications-page/notifications-page.component').then(
            (m) => m.NotificationsPageComponent
          )
      },
      {
        path: 'pricing',
        loadComponent: () =>
          import('@domains/dashboard/features/pricing-page/pricing-page.component').then(
            (m) => m.PricingPageComponent
          )
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('@domains/settings/features/settings-page/settings-page.component').then(
            (m) => m.SettingsPageComponent
          )
      }
    ]
  },
  { path: '**', redirectTo: 'login' }
];
