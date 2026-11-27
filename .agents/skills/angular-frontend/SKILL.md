---
name: angular-frontend
description: Guidelines and verification workflows for KronFlow Angular 21.2 Zoneless SPAs (frontend/app CRM and frontend/landing), including standalone OnPush patterns, API envelopes, session/CSRF handling, WCAG 2.2 AA accessibility, and Vitest/ESLint/build checks.
---

# Angular Frontend Skill — KronFlow

Use this skill whenever editing `frontend/app` (CRM) or `frontend/landing` (public portal). Pair with `.agents/skills/ui-ux-pro-max/SKILL.md` for visual design, layout, and design-system decisions.

## 1. Architecture & Code Conventions

- **Angular 21.2 Zoneless:** Every component must be `standalone: true` and use `ChangeDetectionStrategy.OnPush` with Angular Signals (`signal`, `computed`, `effect`) for reactive state. Never re-introduce Zone.js.
- **Folder boundaries (`frontend/app`):**
  - `src/app/core/`: interceptors, guards, global config.
  - `src/app/domains/<domain>/`: `domain/` (models), `data-access/` (HTTP services), `features/` (routed pages), `ui/` (presentational components).
  - `src/app/shared/`: reusable primitives and utilities (`token-storage.ts`, design tokens).
- **Selectors & Design System:** Use `kronflow-*` selectors, Teal/Emerald/Cyan palette, `Sora` + `Inter` + `JetBrains Mono`, persistent light/dark theme (`localStorage['theme']`), and respect CSS component budgets (`8 kB` warning / `12 kB` error).

## 2. API & Security Rules

- **HTTP transport:** All API calls go through `HttpClient` and `auth.interceptor.ts` (adds `X-Correlation-ID`, `Authorization: Bearer`, `X-Tenant-ID`, and single 401 refresh retry).
- **Envelopes:** Auth and Operational return `ApiResponse<T>` / `ApiError`; unwrap `data` inside `data-access` services, never leak raw envelopes into templates.
- **Session storage:** Keep existing keys `flowkron.access_token`, `flowkron.refresh_token`, `flowkron.tenant_id`, and `theme`. Never inject untrusted HTML (`innerHTML` bypasses) to avoid XSS token exposure.
- **No internal routes:** Frontends never call `/internal/*` and never pass `schema_name`.
- **Landing CSRF:** `frontend/landing` submits contact messages to `POST /api/v1/contact/messages/` with Django CSRF cookie + `X-CSRFToken`.

## 3. Verification Checklist

Run in `frontend/app` and/or `frontend/landing` (Node 24):

```sh
npm run lint
npm test
npm run build
```

All three must exit with `0` errors and `0` warnings. For production dependency security: `npm audit --omit=dev --audit-level=high`.
