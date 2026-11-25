export interface SubscriptionInfo {
  plan: string;
  status: string;
  entitlements: string[];
  current_period_end: string | null;
  requires_paid_plan: boolean;
}

export interface OperationalRuntimeInfo {
  schema_name: string;
  tenant_code: string;
  plan: string;
  status: string;
  provisioned_at: string | null;
  suspended_at: string | null;
  last_sync_at?: string | null;
  last_error?: string;
}

export interface AuthTokenResponse {
  access: string;
  refresh: string;
}

export interface AuthOptions {
  signup_enabled: boolean;
  google_client_id: string;
  google_nonce: string;
}

export interface GoogleLoginRequest {
  credential: string;
  nonce: string;
  mfa_code?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  tenant_id?: number;
  mfa_code?: string;
}

export interface LoginResponse extends AuthTokenResponse {
  session_id: number;
  tenant_id: number | null;
  roles: string[];
  permissions: string[];
  subscription: SubscriptionInfo | null;
  onboarding_required: boolean;
}

export interface UserProfile {
  display_name: string;
  phone?: string;
  avatar_url?: string;
  timezone?: string;
  locale?: string;
  email_verified_at: string | null;
  mfa_enabled: boolean;
  mfa_confirmed_at: string | null;
}

export interface User {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  profile: UserProfile;
}

export interface Tenant {
  id: number;
  slug: string;
  name: string;
  legal_name?: string;
  tax_id?: string;
  logo_url?: string;
  country?: string;
  status: string;
  plan: string;
  subscription_status: string;
  subscription?: SubscriptionInfo;
  operational_runtime?: OperationalRuntimeInfo | null;
}

export type RefreshResponse = AuthTokenResponse;

export interface TenantOnboardingRequest {
  name: string;
  legal_name?: string;
  tax_id?: string;
  country?: string;
}

export interface TenantOnboardingResponse extends AuthTokenResponse {
  tenant: Tenant;
  membership: TenantMembership;
  onboarding_completed_at: string;
  session_id: number;
  tenant_id: number;
  roles: string[];
  permissions: string[];
}

export interface TenantMembership {
  id: number;
  tenant: number;
  user: number;
  user_email: string;
  display_name?: string;
  avatar_url?: string;
  role_codes?: string[];
  status: string;
  joined_at: string | null;
  revoked_at: string | null;
}

export interface TenantInvitation {
  id: number;
  tenant: number;
  tenant_name: string;
  email: string;
  role_code: string;
  status: 'pending' | 'accepted' | 'rejected' | 'expired' | string;
  invited_by_email?: string;
  expires_at: string;
  accepted_at: string | null;
  rejected_at: string | null;
  created_at: string;
}

export interface InviteMemberResponse {
  invitation: TenantInvitation;
  email_sent: boolean;
  token?: string;
  invite_url?: string;
}

export interface ProfileUpdateRequest {
  display_name?: string;
  phone?: string;
  avatar_url?: string;
  timezone?: string;
  locale?: string;
  first_name?: string;
  last_name?: string;
}

export interface TenantUpdateRequest {
  name?: string;
  legal_name?: string;
  tax_id?: string;
  logo_url?: string;
  country?: string;
}

export interface MeResponse {
  user: User;
  tenant: Tenant | null;
  membership: TenantMembership | null;
  roles: string[];
  permissions: string[];
  subscription: SubscriptionInfo | null;
  onboarding_required: boolean;
  session: {
    id: number;
    status: string;
    expires_at: string;
  } | null;
}

export interface AuthError {
  code: string;
  message: string;
  details?: unknown;
}
