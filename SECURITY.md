# Security policy

## Report privately

Use [GitHub's private vulnerability reporting form](https://github.com/Blandskron/KronFlow/security/advisories/new). Include the affected version or commit, the affected component, prerequisites, impact and steps to reproduce with synthetic data. Keep credentials, customer information and exploit details out of public issues.

## Scope

The repository includes IAM, Operational, Agent Core, both Angular apps, the Baileys connector, a transactional email gateway and a local Compose topology. External provider accounts and independently deployed adapters have their own disclosure channels.

Reviewers should pay particular attention to JWT and tenant isolation, public contact and ingest inputs, signing key and internal credential handling, outbound provider traffic, and authentication, sender scoping and idempotency at the email gateway. The optional external adapter owns channel-specific signature validation and consent.

A usable report can describe a reachable boundary failure, affected data or actions, and required access. No additional risks are accepted here. See the [release review](RELEASE_READINESS.md) for open questions about deployment and distribution.

## Incident Response Runbook & Breach Notification SLAs (`PRV-024`)

KronFlow maintains a tenant-scoped incident register (`public.security_incidents`, exposed via `/api/v1/operational/security-incidents`) that automatically computes regulatory notification deadlines from `detected_at`.

> **Important:** Automated SLA tracking assists operational readiness, but **every external notification to CSIRT/ANCI, data protection authorities, or affected data subjects requires explicit human review and legal/DPO sign-off**.

### Regulatory Timelines

| Milestone | Deadline from `detected_at` | Legal Reference | Required Action |
| --- | --- | --- | --- |
| **Triage & Containment** | Immediate (< 1 hour) | ISO/IEC 27001 A.5.24–A.5.26 | Register incident in `/api/v1/operational/security-incidents`, revoke compromised JWTs/keys (`Redis` revocation + key rotation), isolate affected tenant/integration, preserve forensic logs (`log_limpiezas` hash chain + `audit_events`). |
| **Early Warning (CSIRT / ANCI)** | **3 hours** (`csirt_early_warning_due_at`) | Chile **Ley 21.663** (Cybersecurity Framework Law) | Submit preliminary alert to CSIRT Nacional / ANCI when a significant cybersecurity incident impacts essential or covered services. |
| **Authority Breach Notification** | **72 hours** (`authority_notice_due_at`) | **GDPR Art. 33** / Chile **Ley 21.719** (Agencia de Protección de Datos Personales) | Notify competent supervisory authority if personal data confidentiality, integrity, or availability was compromised and risk to individuals is not unlikely. |
| **Affected Data Subjects Notice** | Without undue delay | **GDPR Art. 34** / **Ley 21.719** | Notify impacted individuals in plain language when the breach poses a high risk to their rights and freedoms. |
| **Final Post-Incident Report** | **15 calendar days** | Chile **Ley 21.663** / ISO 27001 A.5.27 | Deliver root-cause analysis, corrective actions, and evidence of remediation; update incident status to `closed`. |

### Notification Templates (Require Legal/DPO Approval)

#### 1. CSIRT / ANCI Early Warning (3h — Ley 21.663)
- **Incident ID & Tenant:** `<incident_id>` / `<tenant_slug>`
- **Detection Timestamp (UTC):** `<detected_at>`
- **Severity & Affected Systems:** `<severity>` — `<services/channels>`
- **Initial Summary & Containment:** `<summary>` / `<containment_notes>`
- **Point of Contact (DPO / Security):** `<dpo_contact_email>`

#### 2. Supervisory Authority Notice (72h — GDPR Art. 33 / Ley 21.719)
- **Nature of Personal Data Breach:** `<confidentiality | integrity | availability>`
- **Categories & Approximate Count of Data Subjects / Records:** `<affected_records_estimate>`
- **DPO / Contact Point:** `<dpo_contact_email>`
- **Likely Consequences:** `<impact assessment>`
- **Measures Taken or Proposed to Mitigate:** `<containment_notes>`
