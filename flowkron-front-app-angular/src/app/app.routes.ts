import { Routes } from '@angular/router';
import { authGuard } from '@core/guards/auth.guard';
import { noAuthGuard } from '@core/guards/no-auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    title: 'Iniciar sesión · Flowkron',
    canActivate: [noAuthGuard],
    loadComponent: () => import('@domains/auth/features/login-page/login-page.component').then((m) => m.LoginComponent)
  },
  {
    path: 'registrarse',
    title: 'Crear cuenta · Flowkron',
    canActivate: [noAuthGuard],
    loadComponent: () =>
      import('@domains/auth/features/signup-page/signup-page.component').then((m) => m.SignupPageComponent)
  },
  {
    path: 'forgot-password',
    title: 'Recuperar contraseña · Flowkron',
    loadComponent: () =>
      import('@domains/auth/features/forgot-password-page/forgot-password-page.component').then((m) => m.ForgotPasswordComponent)
  },
  {
    path: 'confirm-email',
    title: 'Confirmar correo · Flowkron',
    loadComponent: () =>
      import('@domains/auth/features/confirm-email-page/confirm-email-page.component').then((m) => m.ConfirmEmailComponent)
  },
  {
    path: 'reset-password',
    title: 'Nueva contraseña · Flowkron',
    loadComponent: () =>
      import('@domains/auth/features/reset-password-page/reset-password-page.component').then((m) => m.ResetPasswordComponent)
  },
  {
    path: 'onboarding/company',
    title: 'Crear empresa · Flowkron',
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
        title: 'Inicio · Flowkron',
        loadComponent: () =>
          import('@domains/dashboard/features/home-page/home-page.component').then((m) => m.HomePageComponent)
      },
      {
        path: 'business-context',
        title: 'Contexto empresarial · Flowkron',
        loadComponent: () =>
          import('@domains/agents/features/business-context-page/business-context-page.component').then(
            (m) => m.BusinessContextPageComponent
          )
      },

      {
        path: 'conversations',
        title: 'Conversaciones · Flowkron',
        loadComponent: () =>
          import('@domains/conversations/features/chats-page/chats-page.component').then((m) => m.ChatsPageComponent)
      },
      {
        path: 'contacts',
        title: 'Contactos · Flowkron',
        loadComponent: () =>
          import('@domains/contacts/features/contacts-page/contacts-page.component').then((m) => m.ContactsPageComponent)
      },
      {
        path: 'contacts/:id',
        title: 'Ficha de contacto · Flowkron',
        loadComponent: () =>
          import('@domains/contacts/features/contact-detail-page/contact-detail-page.component').then((m) => m.ContactDetailPageComponent)
      },
      {
        path: 'leads',
        title: 'Seguimiento de leads · Flowkron',
        loadComponent: () => import('@domains/leads/features/leads-page/leads-page.component').then((m) => m.LeadsPageComponent)
      },
      {
        path: 'workflows',
        title: 'Oportunidades · Flowkron',
        loadComponent: () =>
          import('@domains/leads/features/workflows-page/workflows-page.component').then(
            (m) => m.WorkflowsPageComponent
          )
      },
      {
        path: 'whatsapp',
        title: 'Conectar WhatsApp · Flowkron',
        loadComponent: () =>
          import('@domains/dashboard/features/whatsapp-page/whatsapp-page.component').then((m) => m.WhatsAppPageComponent)
      },
      { path: 'integrations', redirectTo: 'whatsapp' },
      {
        path: 'analytics',
        title: 'Métricas · Flowkron',
        loadComponent: () =>
          import('@domains/analytics/features/analytics-page/analytics-page.component').then(
            (m) => m.AnalyticsPageComponent
          )
      },
      {
        path: 'notifications',
        title: 'Notificaciones · Flowkron',
        loadComponent: () =>
          import('@domains/dashboard/features/notifications-page/notifications-page.component').then(
            (m) => m.NotificationsPageComponent
          )
      },
      { path: 'pricing', redirectTo: 'home' },
      {
        path: 'settings',
        title: 'Configuración · Flowkron',
        loadComponent: () =>
          import('@domains/settings/features/settings-page/settings-page.component').then(
            (m) => m.SettingsPageComponent
          )
      }
    ]
  },
  { path: '**', redirectTo: 'login' }
];
