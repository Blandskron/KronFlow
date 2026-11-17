from django.contrib import admin
from django.contrib import messages
from django.db import transaction

from .models import Tenant, TenantInvitation, TenantMembership, TenantOperationalRuntime
from .services import activate_subscription, provision_operational_runtime


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "country", "status", "plan", "subscription_status", "created_at"]
    search_fields = ["name", "legal_name", "tax_id", "slug"]
    list_filter = ["status", "plan", "subscription_status", "country"]
    readonly_fields = ["status", "created_at", "updated_at"]
    actions = ["activate_standard_plan", "activate_advanced_plan", "activate_corporate_plan", "set_free_plan"]

    def has_delete_permission(self, request, obj=None):
        # Workspace deletion must also stop its external runtime and connector.
        return False

    def save_model(self, request, obj, form, change):
        if self._should_have_manual_subscription(obj):
            if not obj.subscription_provider:
                obj.subscription_provider = "manual_admin"
            if not obj.subscription_external_id:
                obj.subscription_external_id = f"admin:{request.user.pk}:{obj.pk or 'new'}"

        super().save_model(request, obj, form, change)

        if obj.subscription_external_id.endswith(":new"):
            obj.subscription_external_id = f"admin:{request.user.pk}:{obj.pk}"
            obj.save(update_fields=["subscription_external_id", "updated_at"])

        if not self._should_provision_after_save(obj, form, change):
            return

        tenant_pk = obj.pk
        transaction.on_commit(lambda: self._provision_after_commit(request, tenant_pk))

    @admin.action(description="Activar plan Standard")
    def activate_standard_plan(self, request, queryset):
        self._activate_plan(request, queryset, Tenant.Plan.STARTER, "Standard")

    @admin.action(description="Activar plan Advanced")
    def activate_advanced_plan(self, request, queryset):
        self._activate_plan(request, queryset, Tenant.Plan.PRO, "Advanced")

    @admin.action(description="Activar plan Corporate")
    def activate_corporate_plan(self, request, queryset):
        self._activate_plan(request, queryset, Tenant.Plan.ENTERPRISE, "Corporate")

    @admin.action(description="Volver a plan Free")
    def set_free_plan(self, request, queryset):
        updated = queryset.update(
            plan=Tenant.Plan.FREE,
            subscription_status=Tenant.SubscriptionStatus.FREE,
            subscription_provider="",
            subscription_external_id="",
            subscription_current_period_end=None,
        )
        self.message_user(request, f"{updated} tenant(s) quedaron en plan Free.", messages.SUCCESS)

    def _activate_plan(self, request, queryset, plan, label):
        activated = 0
        failed = []
        for tenant in queryset:
            try:
                activate_subscription(tenant, plan=plan, provider="manual_admin", external_id=f"admin:{request.user.pk}")
                activated += 1
            except Exception as exc:  # noqa: BLE001 - admin action should report per-tenant failures.
                failed.append(f"{tenant.name}: {exc}")

        if activated:
            self.message_user(request, f"{activated} tenant(s) activados en plan {label}.", messages.SUCCESS)
        for error in failed:
            self.message_user(request, error, messages.ERROR)

    def _should_have_manual_subscription(self, tenant):
        return tenant.plan != Tenant.Plan.FREE and tenant.subscription_status in {
            Tenant.SubscriptionStatus.ACTIVE,
            Tenant.SubscriptionStatus.TRIALING,
        }

    def _should_provision_after_save(self, tenant, form, change):
        if not self._should_have_manual_subscription(tenant):
            return False

        if not TenantOperationalRuntime.objects.filter(tenant=tenant).exists():
            return True

        if not change:
            return True

        return bool(
            {
                "plan",
                "subscription_status",
                "subscription_provider",
                "subscription_external_id",
                "subscription_current_period_end",
            }.intersection(set(form.changed_data))
        )

    def _provision_after_commit(self, request, tenant_pk):
        try:
            tenant = Tenant.objects.get(pk=tenant_pk)
            provision_operational_runtime(tenant)
            self.message_user(request, "Runtime/schema operacional provisionado correctamente.", messages.SUCCESS)
        except Exception as exc:  # noqa: BLE001 - admin must keep the tenant save and report provisioning failures.
            self.message_user(request, f"El tenant fue guardado, pero fallo el provisioning operacional: {exc}", messages.ERROR)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "status", "joined_at", "created_at"]
    search_fields = ["user__email", "tenant__name"]
    list_filter = ["status"]


@admin.register(TenantInvitation)
class TenantInvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "tenant", "role_code", "status", "expires_at", "accepted_at", "revoked_at", "created_at"]
    search_fields = ["email", "tenant__name"]
    list_filter = ["status", "role_code"]


@admin.register(TenantOperationalRuntime)
class TenantOperationalRuntimeAdmin(admin.ModelAdmin):
    list_display = ["tenant", "tenant_code", "status", "plan", "provisioned_at", "last_sync_at"]
    search_fields = ["tenant__name", "tenant__slug", "tenant_code", "schema_name"]
    list_filter = ["status", "plan"]
    readonly_fields = ["created_at", "updated_at", "last_sync_at", "last_error"]
