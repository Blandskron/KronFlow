import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { LucideCopy, LucideRefreshCw, LucideSave, LucideSend, LucideTrash2, LucideUpload } from '@lucide/angular';
import { InviteMemberResponse, TenantInvitation, TenantMembership } from '@domains/auth/domain/auth.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { TenantService } from '@domains/auth/data-access/tenant.service';
import { WorkspaceStateService } from '@core/services/workspace-state.service';

type SettingsTab = 'company' | 'profile' | 'team';
type AlertKind = 'success' | 'error' | 'info';

interface AlertState {
  kind: AlertKind;
  text: string;
}

@Component({
  selector: 'kronflow-settings-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, LucideCopy, LucideRefreshCw, LucideSave, LucideSend, LucideTrash2, LucideUpload],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.css'
})
export class SettingsPageComponent implements OnInit {
  readonly workspace = inject(WorkspaceStateService);
  readonly auth = inject(AuthService);
  private readonly tenants = inject(TenantService);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  readonly activeTab = signal<SettingsTab>('company');
  readonly members = signal<TenantMembership[]>([]);
  readonly invitations = signal<TenantInvitation[]>([]);
  readonly companyAlert = signal<AlertState | null>(null);
  readonly profileAlert = signal<AlertState | null>(null);
  readonly teamAlert = signal<AlertState | null>(null);
  readonly lastInviteUrl = signal('');
  readonly teamLoading = signal(false);
  readonly savingCompany = signal(false);
  readonly savingProfile = signal(false);
  readonly uploadingLogo = signal(false);
  readonly uploadingAvatar = signal(false);
  readonly inviting = signal(false);
  readonly pendingRoles = signal<Record<number, string>>({});

  readonly profileInitial = computed(() => this.auth.displayName().charAt(0).toUpperCase());
  readonly tenantInitial = computed(() => (this.auth.currentTenant()?.name || 'X').charAt(0).toUpperCase());
  readonly canManageTenant = computed(() => this.auth.hasPermission('tenants.manage'));
  readonly canManageMembers = computed(() => this.auth.hasPermission('members.manage'));

  readonly tabs: { id: SettingsTab; label: string }[] = [
    { id: 'company', label: 'Empresa' },
    { id: 'profile', label: 'Mi Perfil' },
    { id: 'team', label: 'Equipo' }
  ];

  readonly roleOptions = [
    { code: 'VENDEDOR', label: 'Vendedor' },
    { code: 'TENANT_ADMIN', label: 'Administrador' },
    { code: 'MANAGER', label: 'Manager' },
    { code: 'AGENT_SUPERVISOR', label: 'Supervisor' },
    { code: 'AGENT_OPERATOR', label: 'Operador' },
    { code: 'VIEWER', label: 'Lector' }
  ];

  readonly companyForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    legal_name: [''],
    tax_id: [''],
    country: ['CL', [Validators.maxLength(2)]],
    logo_url: ['']
  });

  readonly profileForm = this.fb.nonNullable.group({
    display_name: [''],
    first_name: [''],
    last_name: [''],
    phone: [''],
    timezone: ['America/Santiago'],
    locale: ['es-CL'],
    avatar_url: ['']
  });

  readonly inviteForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    roleCode: ['VENDEDOR', Validators.required]
  });

  ngOnInit(): void {
    const tab = this.route.snapshot.queryParamMap.get('tab');
    if (tab === 'company' || tab === 'profile' || tab === 'team') {
      this.activeTab.set(tab);
    }

    this.patchCompanyForm();
    this.patchProfileForm();
    if (this.canManageMembers()) {
      this.loadTeam();
    }
  }

  setTab(tab: SettingsTab): void {
    this.activeTab.set(tab);
    if (tab === 'team' && this.canManageMembers() && !this.members().length) {
      this.loadTeam();
    }
  }

  saveCompany(): void {
    const tenant = this.auth.currentTenant();
    if (!tenant || !this.canManageTenant()) {
      this.companyAlert.set({ kind: 'error', text: 'Tu rol actual no permite modificar la empresa.' });
      return;
    }
    if (this.companyForm.invalid) {
      this.companyForm.markAllAsTouched();
      return;
    }

    this.savingCompany.set(true);
    this.companyAlert.set(null);
    this.tenants.updateTenant(tenant.id, this.companyForm.getRawValue()).subscribe({
      next: (updated) => {
        this.auth.setCurrentTenant(updated);
        this.patchCompanyForm();
        this.companyAlert.set({ kind: 'success', text: 'Empresa actualizada.' });
        this.savingCompany.set(false);
      },
      error: () => {
        this.companyAlert.set({ kind: 'error', text: 'No pudimos actualizar la empresa.' });
        this.savingCompany.set(false);
      }
    });
  }

  saveProfile(): void {
    if (this.profileForm.invalid) {
      this.profileForm.markAllAsTouched();
      return;
    }

    this.savingProfile.set(true);
    this.profileAlert.set(null);
    this.auth.updateProfile(this.profileForm.getRawValue()).subscribe({
      next: () => {
        this.patchProfileForm();
        this.profileAlert.set({ kind: 'success', text: 'Perfil actualizado.' });
        this.savingProfile.set(false);
      },
      error: () => {
        this.profileAlert.set({ kind: 'error', text: 'No pudimos actualizar tu perfil.' });
        this.savingProfile.set(false);
      }
    });
  }

  uploadCompanyLogo(event: Event): void {
    const tenant = this.auth.currentTenant();
    const file = this.fileFromEvent(event);
    if (!tenant || !file) {
      return;
    }

    this.uploadingLogo.set(true);
    this.companyAlert.set(null);
    this.tenants.uploadTenantLogo(tenant.id, file).subscribe({
      next: (updated) => {
        this.auth.setCurrentTenant(updated);
        this.patchCompanyForm();
        this.companyAlert.set({ kind: 'success', text: 'Logo actualizado.' });
        this.uploadingLogo.set(false);
      },
      error: () => {
        this.companyAlert.set({ kind: 'error', text: 'No pudimos subir el logo.' });
        this.uploadingLogo.set(false);
      }
    });
  }

  uploadAvatar(event: Event): void {
    const file = this.fileFromEvent(event);
    if (!file) {
      return;
    }

    this.uploadingAvatar.set(true);
    this.profileAlert.set(null);
    this.auth.uploadAvatar(file).subscribe({
      next: () => {
        this.patchProfileForm();
        this.profileAlert.set({ kind: 'success', text: 'Foto actualizada.' });
        this.uploadingAvatar.set(false);
      },
      error: () => {
        this.profileAlert.set({ kind: 'error', text: 'No pudimos subir la foto.' });
        this.uploadingAvatar.set(false);
      }
    });
  }

  loadTeam(): void {
    const tenantId = this.auth.getTenantId();
    if (!tenantId || !this.canManageMembers()) {
      return;
    }

    this.teamLoading.set(true);
    this.teamAlert.set(null);
    this.tenants.listMembers(tenantId).subscribe({
      next: (members) => {
        this.members.set(members);
        this.pendingRoles.set(Object.fromEntries(members.map((member) => [member.id, this.primaryRole(member)])));
        this.loadInvitations(tenantId);
      },
      error: () => {
        this.teamAlert.set({ kind: 'error', text: 'No pudimos cargar el equipo.' });
        this.teamLoading.set(false);
      }
    });
  }

  inviteMember(): void {
    const tenantId = this.auth.getTenantId();
    if (!tenantId || this.inviteForm.invalid) {
      this.inviteForm.markAllAsTouched();
      return;
    }

    const value = this.inviteForm.getRawValue();
    this.inviting.set(true);
    this.teamAlert.set(null);
    this.lastInviteUrl.set('');
    this.tenants
      .inviteMember(tenantId, {
        email: value.email,
        role_code: value.roleCode,
        expires_in_days: 7
      })
      .subscribe({
        next: (result) => this.handleInviteResult(result, tenantId),
        error: () => {
          this.teamAlert.set({ kind: 'error', text: 'No pudimos crear la invitacion.' });
          this.inviting.set(false);
        }
      });
  }

  setPendingRole(memberId: number, event: Event): void {
    const select = event.target as HTMLSelectElement;
    this.pendingRoles.update((roles) => ({ ...roles, [memberId]: select.value }));
  }

  saveMemberRole(member: TenantMembership): void {
    const tenantId = this.auth.getTenantId();
    const roleCode = this.pendingRoles()[member.id] || this.primaryRole(member);
    if (!tenantId || this.isCurrentUser(member)) {
      return;
    }

    this.tenants.updateMember(tenantId, member.id, { role_codes: [roleCode] }).subscribe({
      next: (updated) => {
        this.members.update((members) => members.map((item) => (item.id === updated.id ? updated : item)));
        this.teamAlert.set({ kind: 'success', text: 'Rol actualizado.' });
      },
      error: () => this.teamAlert.set({ kind: 'error', text: 'No pudimos actualizar el rol.' })
    });
  }

  removeMember(member: TenantMembership): void {
    const tenantId = this.auth.getTenantId();
    if (!tenantId || this.isCurrentUser(member)) {
      return;
    }

    this.tenants.removeMember(tenantId, member.id).subscribe({
      next: (updated) => {
        this.members.update((members) => members.map((item) => (item.id === updated.id ? updated : item)));
        this.teamAlert.set({ kind: 'success', text: 'Miembro revocado.' });
      },
      error: () => this.teamAlert.set({ kind: 'error', text: 'No pudimos revocar al miembro.' })
    });
  }

  copyInviteUrl(): void {
    const value = this.lastInviteUrl();
    if (!value || !navigator.clipboard) {
      return;
    }
    void navigator.clipboard.writeText(value);
    this.teamAlert.set({ kind: 'info', text: 'Enlace copiado.' });
  }

  primaryRole(member: TenantMembership): string {
    return member.role_codes?.[0] || 'VIEWER';
  }

  roleLabel(roleCode: string): string {
    return this.roleOptions.find((role) => role.code === roleCode)?.label || roleCode;
  }

  memberInitial(member: TenantMembership): string {
    return (member.display_name || member.user_email || '?').charAt(0).toUpperCase();
  }

  isCurrentUser(member: TenantMembership): boolean {
    return member.user === this.auth.currentUser()?.id;
  }

  private loadInvitations(tenantId: number): void {
    this.tenants.listInvitations(tenantId).subscribe({
      next: (invitations) => {
        this.invitations.set(invitations);
        this.teamLoading.set(false);
      },
      error: () => {
        this.teamAlert.set({ kind: 'error', text: 'No pudimos cargar las invitaciones.' });
        this.teamLoading.set(false);
      }
    });
  }

  private handleInviteResult(result: InviteMemberResponse, tenantId: number): void {
    this.inviteForm.reset({ email: '', roleCode: 'VENDEDOR' });
    this.invitations.update((invitations) => [result.invitation, ...invitations.filter((item) => item.id !== result.invitation.id)]);
    if (result.invite_url) {
      this.lastInviteUrl.set(result.invite_url);
      this.teamAlert.set({ kind: 'info', text: 'Invitacion creada. Usa el enlace local si el correo no salio por SMTP.' });
    } else {
      this.teamAlert.set({ kind: 'success', text: result.email_sent ? 'Invitacion enviada.' : 'Invitacion creada.' });
    }
    this.inviting.set(false);
    this.loadInvitations(tenantId);
  }

  private patchCompanyForm(): void {
    const tenant = this.auth.currentTenant();
    if (!tenant) {
      return;
    }
    this.companyForm.patchValue({
      name: tenant.name || '',
      legal_name: tenant.legal_name || '',
      tax_id: tenant.tax_id || '',
      country: tenant.country || 'CL',
      logo_url: tenant.logo_url || ''
    });
  }

  private patchProfileForm(): void {
    const user = this.auth.currentUser();
    if (!user) {
      return;
    }
    this.profileForm.patchValue({
      display_name: user.profile.display_name || '',
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      phone: user.profile.phone || '',
      timezone: user.profile.timezone || 'America/Santiago',
      locale: user.profile.locale || 'es-CL',
      avatar_url: user.profile.avatar_url || ''
    });
  }

  private fileFromEvent(event: Event): File | null {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    return file;
  }
}
