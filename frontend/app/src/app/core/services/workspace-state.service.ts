import { Injectable, computed, inject, signal } from '@angular/core';
import { AgentData } from '@domains/onboarding/domain/agent.model';
import { CompanyData } from '@domains/onboarding/domain/company.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

@Injectable({ providedIn: 'root' })
export class WorkspaceStateService {
  private readonly auth = inject(AuthService);
  private readonly localCompany = signal<CompanyData | null>(null);
  readonly company = computed<CompanyData | null>(() => {
    const tenant = this.auth.currentTenant();
    if (tenant) {
      return {
        companyName: tenant.name,
        industry: tenant.country || 'No definido',
        teamSize: tenant.plan
      };
    }
    return this.localCompany();
  });
  readonly agents = signal<AgentData[]>([]);
  readonly userName = computed(() => this.auth.displayName());

  setCompany(company: CompanyData): void {
    this.localCompany.set(company);
  }

  addAgent(agent: AgentData): void {
    this.agents.update((agents) => [...agents, agent]);
  }

  logout(): void {
    this.localCompany.set(null);
    this.agents.set([]);
  }
}
