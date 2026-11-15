import { Component, OnInit, computed, inject } from '@angular/core';
import {
  LucideBarChart3,
  LucideBell,
  LucideBookOpen,
  LucideHome,
  LucideLink,
  LucideLogOut,
  LucideMessageSquare,
  LucideUser,
  LucideWorkflow
} from '@lucide/angular';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { WorkspaceStateService } from '@core/services/workspace-state.service';
import { ThemeToggleComponent } from '@shared/ui/theme-toggle.component';

@Component({
  selector: 'flowkron-dashboard-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ThemeToggleComponent,
    LucideHome,
  LucideLink,
    LucideMessageSquare,
    LucideWorkflow,
    LucideBarChart3,
    LucideBell,
    LucideUser,
    LucideLogOut,
    LucideBookOpen
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
  readonly brandName = computed(() => this.auth.currentTenant()?.name || 'Flowkron');

  readonly navItems = [
    { path: '/app/home', label: 'Inicio', icon: 'home' },
    { path: '/app/conversations', label: 'Bandeja', icon: 'message-square' },
    { path: '/app/whatsapp', label: 'WhatsApp', icon: 'link' },
    { path: '/app/business-context', label: 'Contexto', icon: 'book-open' },
    { path: '/app/workflows', label: 'Oportunidades', icon: 'workflow' },
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
