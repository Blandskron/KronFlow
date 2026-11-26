import { Routes } from '@angular/router';
import { authGuard } from '@core/guards/auth.guard';
import { noAuthGuard } from '@core/guards/no-auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    title: 'Iniciar sesión · KronFlow',
    canActivate: [noAuthGuard],
    loadComponent: () => import('@domains/auth/features/login-page/login-page.component').then((m) => m.LoginComponent)
  },
  {
    path: 'registrarse',
    title: 'Crear cuenta · KronFlow',
    canActivate: [noAuthGuard],
    loadComponent: () =>
      import('@domains/auth/features/signup-page/signup-page.component').then((m) => m.SignupPageComponent)
  },
  {
    path: 'forgot-password',
    title: 'Recuperar contraseña · KronFlow',
    loadComponent: () =>
      import('@domains/auth/features/forgot-password-page/forgot-password-page.component').then((m) => m.ForgotPasswordComponent)
  },
  {
    path: 'confirm-email',
    title: 'Confirmar correo · KronFlow',
    loadComponent: () =>
      import('@domains/auth/features/confirm-email-page/confirm-email-page.component').then((m) => m.ConfirmEmailComponent)
  },
  {
    path: 'reset-password',
    title: 'Nueva contraseña · KronFlow',
    loadComponent: () =>
      import('@domains/auth/features/reset-password-page/reset-password-page.component').then((m) => m.ResetPasswordComponent)
  },
  {
    path: 'onboarding/company',
    title: 'Crear empresa · KronFlow',
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
        title: 'Inicio · KronFlow',
        loadComponent: () =>
          import('@domains/dashboard/features/home-page/home-page.component').then((m) => m.HomePageComponent)
      },
      {
        path: 'business-context',
        title: 'Contexto empresarial · KronFlow',
        loadComponent: () =>
          import('@domains/agents/features/business-context-page/business-context-page.component').then(
            (m) => m.BusinessContextPageComponent
          )
      },
      {
        path: 'agents',
        title: 'Agentes IA · KronFlow',
        loadComponent: () =>
          import('@domains/agents/features/agents-page/agents-page.component').then((m) => m.AgentsPageComponent)
      },
      {
        path: 'tools',
        title: 'Herramientas y Webchat · KronFlow',
        loadComponent: () =>
          import('@domains/agents/features/tools-hub-page/tools-hub-page.component').then(
            (m) => m.ToolsHubPageComponent
          )
      },
      {
        path: 'conversations',
        title: 'Conversaciones · KronFlow',
        loadComponent: () =>
          import('@domains/conversations/features/chats-page/chats-page.component').then((m) => m.ChatsPageComponent)
      },
      {
        path: 'contacts',
        title: 'Contactos · KronFlow',
        loadComponent: () =>
          import('@domains/contacts/features/contacts-page/contacts-page.component').then((m) => m.ContactsPageComponent)
      },
      {
        path: 'contacts/new',
        title: 'Nuevo contacto · KronFlow',
        loadComponent: () =>
          import('@domains/contacts/features/contact-create-page/contact-create-page.component').then((m) => m.ContactCreatePageComponent)
      },
      {
        path: 'contacts/:id',
        title: 'Ficha de contacto · KronFlow',
        loadComponent: () =>
          import('@domains/contacts/features/contact-detail-page/contact-detail-page.component').then((m) => m.ContactDetailPageComponent)
      },
      {
        path: 'leads',
        title: 'Seguimiento de leads · KronFlow',
        loadComponent: () => import('@domains/leads/features/leads-page/leads-page.component').then((m) => m.LeadsPageComponent)
      },
      {
        path: 'leads/:id',
        title: 'Ficha del lead · KronFlow',
        loadComponent: () => import('@domains/leads/features/lead-detail-page/lead-detail-page.component').then((m) => m.LeadDetailPageComponent)
      },
      {
        path: 'workflows',
        title: 'Oportunidades · KronFlow',
        loadComponent: () =>
          import('@domains/leads/features/workflows-page/workflows-page.component').then(
            (m) => m.WorkflowsPageComponent
          )
      },
      {
        path: 'opportunities',
        title: 'Pipeline de oportunidades · KronFlow',
        loadComponent: () =>
          import('@domains/leads/features/opportunities-page/opportunities-page.component').then(
            (m) => m.OpportunitiesPageComponent
          )
      },
      {
        path: 'ai-proposals',
        title: 'Revisión de propuestas IA · KronFlow',
        loadComponent: () =>
          import('@domains/agents/features/ai-proposals-page/ai-proposals-page.component').then(
            (m) => m.AIProposalsPageComponent
          )
      },
      {
        path: 'campaigns',
        title: 'Campañas y canales · KronFlow',
        loadComponent: () =>
          import('@domains/campaigns/features/campaigns-page/campaigns-page.component').then(
            (m) => m.CampaignsPageComponent
          )
      },
      {
        path: 'whatsapp',
        title: 'Conectar WhatsApp · KronFlow',
        loadComponent: () =>
          import('@domains/dashboard/features/whatsapp-page/whatsapp-page.component').then((m) => m.WhatsAppPageComponent)
      },
      { path: 'integrations', redirectTo: 'whatsapp' },
      {
        path: 'analytics',
        title: 'Métricas · KronFlow',
        loadComponent: () =>
          import('@domains/analytics/features/analytics-page/analytics-page.component').then(
            (m) => m.AnalyticsPageComponent
          )
      },
      {
        path: 'notifications',
        title: 'Notificaciones · KronFlow',
        loadComponent: () =>
          import('@domains/dashboard/features/notifications-page/notifications-page.component').then(
            (m) => m.NotificationsPageComponent
          )
      },
      { path: 'pricing', redirectTo: 'home' },
      {
        path: 'settings/audit-events',
        title: 'Eventos de auditoría · KronFlow',
        loadComponent: () => import('@domains/settings/features/audit-events-page/audit-events-page.component')
          .then((m) => m.AuditEventsPageComponent)
      },
      {
        path: 'settings/privacy',
        title: 'Solicitudes de privacidad · KronFlow',
        loadComponent: () => import('@domains/settings/features/privacy-cases-page/privacy-cases-page.component')
          .then((m) => m.PrivacyCasesPageComponent)
      },
      {
        path: 'settings',
        title: 'Configuración · KronFlow',
        loadComponent: () =>
          import('@domains/settings/features/settings-page/settings-page.component').then(
            (m) => m.SettingsPageComponent
          )
      }
    ]
  },
  { path: '**', redirectTo: 'login' }
];
