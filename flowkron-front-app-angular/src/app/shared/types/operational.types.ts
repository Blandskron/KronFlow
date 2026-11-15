export interface OperationalRuntime {
  schema_name: string;
  tenant_code: string;
  plan: string;
  status: string;
  provisioned_at: string | null;
  suspended_at: string | null;
  last_sync_at?: string | null;
  last_error?: string;
}
