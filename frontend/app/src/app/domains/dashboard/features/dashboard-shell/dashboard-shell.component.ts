import { ChangeDetectionStrategy, Component, OnInit, computed, inject } from '@angular/core';
import {
  LucideBarChart3,
  LucideBell,
  LucideBookOpen,
  LucideBot,
  LucideHome,
  LucideLogOut,
  LucideMegaphone,
  LucideMessageSquare,
  LucidePlug,
  LucideSmartphone,
  LucideSparkles,
  LucideUser,
  LucideUsers,
  LucideWorkflow
} from '@lucide/angular';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { WorkspaceStateService } from '@core/services/workspace-state.service';
import { ThemeToggleComponent, ToastContainerComponent } from '@shared/ui';

@Component({
  selector: 'kronflow-dashboard-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ThemeToggleComponent,
    ToastContainerComponent,
    LucideHome,
    LucideSmartphone,
    LucideMessageSquare,
    LucideWorkflow,
    LucideBarChart3,
    LucideBell,
    LucideUser,
    LucideUsers,
    LucideLogOut,
    LucideBookOpen,
    LucideBot,
    LucideMegaphone,
    LucidePlug,
    LucideSparkles
  ],
  templateUrl: './dashboard-shell.component.html',
  styleUrl: './dashboard-shell.component.css'
})
export class DashboardShellComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly workspace = inject(WorkspaceStateService);
  private readonly auth = inject(AuthService);
  readonly notificationCount = computed(() => 0);
  readonly tenantLogo = computed(() => this.auth.currentTenant()?.logo_url || '');
  readonly brandName = computed(() => this.auth.currentTenant()?.name || 'KronFlow');

  readonly navItems = [
    { path: '/app/home', label: 'Inicio', icon: 'home' },
    { path: '/app/conversations', label: 'Bandeja', icon: 'message-square' },
    { path: '/app/contacts', label: 'Contactos', icon: 'users' },
    { path: '/app/whatsapp', label: 'WhatsApp', icon: 'smartphone' },
    { path: '/app/business-context', label: 'Contexto', icon: 'book-open' },
    { path: '/app/agents', label: 'Agentes', icon: 'bot' },
    { path: '/app/tools', label: 'Herramientas', icon: 'plug' },
    { path: '/app/opportunities', label: 'Pipeline', icon: 'workflow' },
    { path: '/app/campaigns', label: 'Campañas', icon: 'megaphone' },
    { path: '/app/ai-proposals', label: 'Propuestas IA', icon: 'sparkles' },
    { path: '/app/analytics', label: 'Métricas', icon: 'bar-chart-3' }
  ];

  ngOnInit(): void {
    this.auth.loadCurrentUser().subscribe({ error: () => undefined });
  }

  logout(): void {
    this.workspace.logout();
    this.auth.logout().subscribe({
      next: () => void this.router.navigate(['/login'])
    });
  }
}
