# Angular Improvement Roadmap — Flowkron Frontend (`app` + `landing`)

> **Fecha de auditoría:** 2026-11-23  
> **Alcance:** `flowkron-front-app-angular` (SPA privada CRM) y `flowkron-front-landing-angular` (SPA pública Landing)  
> **Stack real verificado:** Angular `^21.2.26` · TypeScript `~5.9.3` · RxJS `~7.8.0` · `@lucide/angular ^1.23.0` · `@angular-devkit/build-angular ^21.2.18` · `zone.js ~0.15.0`  
> **Estado actual:** **Roadmap completado (Etapas 0–6 DONE y validadas)** — ambos frontends Angular 21 operan en modo Zoneless + 100% `OnPush`, Design System unificado, Vitest + ESLint en verde e integrados en CI.

---

## 1. Resumen Ejecutivo y Diagnóstico Cuantitativo

Ambos frontends parten de una base moderna en versión de framework (**Angular 21.2.26**), con **100% Standalone Components**, **100% control flow nativo (`@if`/`@for`/`@switch`, 0 usos legacy de `*ngIf`/`*ngFor`)**, **lazy loading por ruta (`loadComponent`)**, y compilación estricta de TypeScript (`strict: true`, `strictTemplates: true`).

Sin embargo, la auditoría reveló brechas estructurales importantes que impiden escalar con calidad enterprise:

| Dimensión / Métrica | `flowkron-front-app-angular` (CRM) | `flowkron-front-landing-angular` (Landing) | Diagnóstico |
|---|---|---|---|
| Archivos `.ts` / Componentes | 70 TS · 32 componentes · 23 HTML · 19 CSS | 11 TS · 5 componentes · 3 HTML · 3 CSS | CRM ya tiene escala media-alta con varios "God Components". |
| `ChangeDetectionStrategy.OnPush` | **0 / 32 (0%)** | **0 / 5 (0%)** | Todo corre en `Default` CD + `zone.js`. |
| `standalone: true` redundante | 29 archivos | 5 archivos | En Angular 19–21 `standalone` es `true` por defecto. |
| `@Input()` / `@Output()` legacy vs `input()` / `output()` | 4 legacy (`legal-modal.component.ts`) · 4 signals | 0 legacy · 2 signals (`legal-modal.component.ts`) | Desalineación entre ambos `shared/ui`. |
| `@angular/animations` en `dependencies` | Instalado + `provideAnimationsAsync()` en `app.config.ts`, **0 animaciones usadas** | Instalado en `package.json`, **0 usos** | Paquete deprecado en Angular 21 y peso muerto en config/deps. |
| Builder y Testing (`ng test`) | `@angular-devkit/build-angular` · **sin target `test`** (`npm test` falla) | `@angular-devkit/build-angular` · **sin target `test`** (`npm test` falla) | **0 tests unitarios** en ambos proyectos; solo smoke Playwright manual. |
| Linting / Formatting | **Sin ESLint / Prettier** | **Sin ESLint / Prettier** | Sin guardrails automáticos de estilo, a11y o arquitectura. |
| Presupuestos CSS (`angular.json`) | **`business-context-page.component.css` = 11.94 kB** (excede warning de 8 kB, al borde del error de 12 kB) | Dentro de presupuesto | Riesgo inminente de ruptura de build. |
| Inline `style="..."` en templates | **37 ocurrencias** en 4 archivos (`campaigns`, `opportunities`, `ai-proposals`, `chats`) | 0 ocurrencias | Quiebra la consistencia del Design System y el soporte de temas. |
| `any` explícitos | **9 ocurrencias** en 3 archivos (`agent-core.service`, `agent-core.model`, `business-context-page`) | 0 ocurrencias | Debilita el tipado estricto en el dominio `agents`. |
| Formularios (`Reactive` vs `FormsModule`) | 7 `ReactiveFormsModule` + **1 `FormsModule` (`CommonModule`)** en `business-context-page` | 1 `ReactiveFormsModule` | Mezcla innecesaria de paradigmas en CRM. |
| Accesibilidad (WCAG 2.2 AA) | 2 `<div (click)>` sin teclado (`legal-modal`, `business-context-page`), modal no nativo sin focus trap ni `Escape`, ícono faltante en nav `Propuestas IA` | `<dialog>` nativo correcto, pero `@import` bloqueante de Google Fonts en CSS | Brechas de foco/teclado en CRM y drift visual entre ambas apps. |
| Duplicación entre apps | `src/styles.css` (336 líneas), `ThemeService`, `ThemeToggleComponent`, `LegalModalComponent` | `src/styles.css` (338 líneas), `ThemeService`, `ThemeToggleComponent`, `LegalModalComponent` | Drift activo: Landing usa `Manrope` (Google Fonts `@import`), CRM usa `Inter` (sin cargar fuente); `LegalModal` divergente. |

---

## 2. Fortalezas Existentes a Preservar (No Regresionar)

Antes de refactorizar, se identifican decisiones sólidas que **deben mantenerse intactas**:

1. **Identidad visual Glassmorphism + Light/Dark Theme:** La paleta de tokens en `:root` y `.dark`, las superficies `.glass-surface` con `@supports (backdrop-filter: blur(1px))` y los media queries `@media (prefers-reduced-transparency: reduce)` y `@media (prefers-reduced-motion: reduce)` son sobresalientes y coherentes con la marca Flowkron.
2. **Estructura `core/` + `domains/` + `shared/` + path aliases (`@core/*`, `@domains/*`, `@shared/*`, `@env/*`):** Ya existe una base limpia de bounded contexts (`agents`, `analytics`, `auth`, `campaigns`, `contacts`, `conversations`, `dashboard`, `leads`, `onboarding`, `settings` en CRM; `landing`, `legal` en Landing).
3. **100% Control Flow moderno (`@if`, `@for`, `@switch`) y Lazy Loading (`loadComponent`):** No hay deuda de `NgModules` ni directivas estructurales antiguas.
4. **Seguridad y resiliencia en Auth (`flowkron-front-app-angular`):**
   - `AuthService.refreshSession()` ya serializa refrescos concurrentes con `this.refreshRequest$` + `shareReplay({ bufferSize: 1, refCount: false })`.
   - `authInterceptor` agrega `X-Correlation-ID` (`crypto.randomUUID()`), `Authorization` y `X-Tenant-ID` selectivamente por origen API.
   - `0` usos de `innerHTML` o `bypassSecurityTrust*` en ambos repositorios.
5. **Formularios accesibles en Landing y módulos recientes:** `landing-page.component.html` ya implementa `aria-invalid`, `aria-describedby`, `role="status"`/`role="alert"`, `autofocus` en `<dialog>` nativo y foco automático al primer campo inválido.
6. **Contratos HTTP y funcionalidades de negocio:** Todas las rutas, endpoints (`/api/v1/*`, operational, agent-core), guards (`authGuard`, `noAuthGuard`), y flujos HITL / campañas / pipeline / privacidad / auditoría deben permanecer 100% funcionales.

---

## 3. Evaluación de Skill Especializada en UI/UX y Estándares

- **Búsqueda en Marketplace:** Se consultó el catálogo oficial (`search_marketplace`) con `["frontend design", "ui ux design system", "angular"]` y no existen plugins/skills externos instalados ni disponibles en el marketplace para diseño frontend Angular.
- **Skills locales existentes:** Ambos repositorios incluyen 4 skills locales en `skills/`: `code-review`, `testing`, `docs-maintenance` y `release`.
- **Recomendación pragmática:** En la **Etapa 3 (Design System & UI/UX)** se creará una skill local reutilizable `skills/frontend-design-system/SKILL.md` (documentando tokens, jerarquía tipográfica, espaciado, variantes de componentes atómicos, microinteracciones con `prefers-reduced-motion` y checklist WCAG 2.2 AA) para que futuras iteraciones y revisiones de código apliquen el mismo estándar de diseño de forma consistente.

---

## 4. Decisiones Técnicas Verificadas con Documentación Oficial de Angular 21

Todas las recomendaciones se contrastaron con `angular.dev` para **Angular 21**:

| Tecnología / Práctica | Decisión | Justificación técnica (Angular 21 oficial) |
|---|---|---|
| **Zoneless (`provideZonelessChangeDetection`) + `OnPush`** | **ADOPTAR** (progresivo: primero `OnPush` + Signals, luego retirar `zone.js`) | En Angular 21 Zoneless es el modelo estándar de producción. Elimina el overhead de `zone.js` (~35 kB) y hace explícito el grafo reactivo. |
| **Vitest (`ng test` con `@angular/build:unit-test`)** | **ADOPTAR** | Vitest es el runner oficial por defecto en Angular 21 (reemplaza Karma/Jasmine), nativo ESM, veloz y compatible con `provideZonelessChangeDetection()`. |
| **Migración de `@angular-devkit/build-angular` a `@angular/build`** | **ADOPTAR** | `@angular/build` es el builder oficial actual (esbuild/Vite), más ligero y requisito limpio para el builder `unit-test` con Vitest. |
| **Retirar `@angular/animations` y `provideAnimationsAsync()`** | **ADOPTAR** | `@angular/animations` está deprecado en Angular 21. Ninguna de las dos apps lo utiliza; las transiciones se manejan con CSS nativo y, si se requieren entradas/salidas, `animate.enter` / `animate.leave`. |
| **Signal Inputs/Outputs (`input()`, `output()`, `model()`) y `computed()`** | **ADOPTAR** | Estables en Angular 21, compatibles con Zoneless/OnPush y eliminan boilerplate de `@Input`/`@Output`. |
| **Signal Forms (`@angular/forms/signals`)** | **NO ADOPTAR (aún)** | Sigue siendo experimental en Angular 21. Estandarizamos en **Reactive Forms tipados (`FormBuilder.nonNullable`)** ya probados en producción y compatibles con Zoneless. |
| **NgRx / Redux Store global** | **NO ADOPTAR** | Sobreingeniería para el tamaño del CRM. **Signal Stores / Facades por dominio** (`@Injectable` con `signal`/`computed` + `rxResource` o RxJS encapsulado) cubren el 100% de las necesidades con mínima complejidad. |
| **Tailwind CSS / Material / PrimeNG** | **NO ADOPTAR** | Reescribir el CSS existente rompería la identidad visual glassmorphism y añadiría dependencias pesadas. Es preferible consolidar el sistema actual de **CSS Design Tokens + componentes atómicos propios**. |
| **Monorepo Nx / Turborepo** | **NO ADOPTAR** | Ambos frontends tienen `Dockerfile`, CI y ciclo de despliegue independientes. Los tokens y primitivos UI compartidos pueden mantenerse sincronizados con una convención clara (y/o contrato de tokens verificable) sin introducir complejidad de build innecesaria. |

---

## 5. Arquitectura Objetivo

### 5.1 Capas por Dominio (Feature-Based + Clean Architecture + DDD Frontend)

```text
src/app/
├── core/                         # Singleton app-wide infrastructure
│   ├── config/                   # API base URLs, feature flags, tokens DI
│   ├── guards/                   # authGuard, noAuthGuard, role/permission guards
│   ├── interceptors/             # authInterceptor, errorNormalizationInterceptor
│   ├── services/                 # ThemeService, WorkspaceStateService, ToastService
│   └── utils/                    # token-storage, http-error normalizer
├── shared/
│   ├── ui/                       # Design System (Atomic Design)
│   │   ├── atoms/                # fk-button, fk-badge, fk-input, fk-spinner, fk-icon
│   │   ├── molecules/            # fk-field, fk-empty-state, fk-alert, fk-stat-card, fk-tabs, fk-pagination
│   │   └── organisms/            # fk-dialog (nativo <dialog>), fk-data-table, fk-page-header, fk-theme-toggle
│   ├── directives/               # focus-trap, click-outside, etc. (solo si aporta valor real)
│   ├── pipes/                    # formateo de fechas, moneda, estados
│   └── types/                    # ApiResponse, PaginatedResponse, OperationalError
└── domains/<bounded-context>/    # agents, analytics, auth, campaigns, contacts, conversations, dashboard, leads, onboarding, settings
    ├── domain/                   # Modelos TypeScript puros, value objects, validadores puros (0 deps de Angular)
    ├── data-access/              # API services (HTTP) + Facades reactivas con Signals
    ├── ui/                       # Componentes presentacionales puros (OnPush, input()/output(), sin HttpClient)
    └── features/                 # Smart pages (rutas lazy, orquestación mínima, <200 líneas TS)
```

### 5.2 Reglas de Dependencia (Boundaries)
1. `domain/` **no importa nada** de `data-access/`, `ui/`, `features/`, ni `@angular/*` (salvo validadores puros si aplica).
2. `ui/` (tanto `shared/ui` como `domains/*/ui`) es **100% presentacional**: `ChangeDetectionStrategy.OnPush`, solo `input()`/`output()`/`model()`, sin inyectar servicios HTTP ni `Router` (salvo `RouterLink`).
3. `features/` (Smart Components) delega estado complejo y llamadas HTTP a `data-access/` y delega marcado repetitivo a `ui/` y `shared/ui/`.
4. Ningún dominio importa archivos internos de otro dominio; si algo es transversal (`AuthService`, tipos compartidos), vive en `core/` o se expone vía barrel público `index.ts`.

### 5.3 Sistema de Diseño Unificado (`app` + `landing`)
Estructurar `src/styles/` en capas limpias e idénticas entre ambas apps:
- `styles/tokens.css`: paleta semántica (light/dark), tipografía (`Manrope` / `Inter` cargada de forma consistente sin `@import` bloqueante), escala de espaciado (`--space-1` a `--space-12`), radios (`--radius-sm/md/lg/pill`), elevaciones/glass, z-index (`--z-base`, `--z-sticky`, `--z-overlay`, `--z-modal`, `--z-toast`), duraciones/easings de movimiento.
- `styles/reset.css`: box-sizing, tipografía base, enlaces, accesibilidad (`:focus-visible`, `.sr-only`, `.skip-link`, `prefers-reduced-motion`, `prefers-reduced-transparency`).
- `styles/primitives.css`: utilidades base mínimas (`.container`, `.glass-surface`, `.card`, `.btn`, `.badge`, `.field`) alineadas con los componentes atómicos de `shared/ui/`.

---

## 6. Catálogo de Problemas Detectados (Priorizados)

### P0 — Críticos (Impacto directo en estabilidad, testing, build o UX rota)
1. **Testing unitario inoperante (`npm test` falla en ambos proyectos):** `angular.json` carece de target `test` y no hay specs unitarios. Impide refactorizar con red de seguridad.
2. **Bug visual en sidebar de CRM (`dashboard-shell.component.html`):** El ítem `Propuestas IA` define `icon: 'bell'` en `navItems` (`dashboard-shell.component.ts:57`), pero `@switch (item.icon)` no tiene `@case ('bell')` → se renderiza sin ícono.
3. **Presupuesto CSS excedido en CRM:** `business-context-page.component.css` pesa `19.8 kB` fuente (`11.94 kB` compilado), superando el límite `maximumWarning: 8kB` y a 60 B de romper el build (`maximumError: 12kB`).
4. **Modal accesible roto en CRM (`flowkron-front-app-angular/src/app/shared/ui/legal-modal.component.ts`):** Usa `<div class="modal-backdrop" (click)="close.emit()">` sin `<dialog>`, sin `role="dialog"`, sin `aria-modal="true"`, sin cierre con tecla `Escape` y sin gestión de foco. Mientras tanto, Landing ya tiene una implementación correcta con `<dialog>` nativo.
5. **Sin Linting ni guardrails de calidad:** Ninguna de las dos apps tiene ESLint (`angular-eslint`) ni Prettier, permitiendo que regresen `any`, `standalone: true`, `FormsModule` o problemas de a11y en templates.

### P1 — Altos (Arquitectura, rendimiento Angular 21 y Design System)
6. **`0%` de componentes con `OnPush` y dependencia activa de `zone.js`:** Los 37 componentes (32 CRM + 5 Landing) usan detección `Default`, impidiendo habilitar `provideZonelessChangeDetection()`.
7. **Dependencia deprecada `@angular/animations`:** Presente en ambos `package.json` y registrada con `provideAnimationsAsync()` en `flowkron-front-app-angular/src/app/app.config.ts` sin ningún uso real.
8. **God Components en CRM que mezclan estado, formularios, HTTP y UI:**
   - `business-context-page`: 574 líneas TS + 421 HTML + 733 CSS (3 pestañas completas: Resumen, Carga/Plantillas/Asistente IA, Simulador; usa `CommonModule` + `FormsModule` + `setInterval` manual + 5 `any`).
   - `chats-page`: 487 líneas TS (inbox, filtros, hilos, HITL bar con inline styles).
   - `settings-page`: 332 líneas TS + 253 HTML + 245 CSS (múltiples pestañas en un solo componente).
   - `contact-detail-page`: 255 líneas TS con template inline.
9. **37 atributos `style="..."` inline y 9 templates inline en páginas nuevas del CRM:** `campaigns-page.component.ts` (15 inline styles), `opportunities-page.component.ts` (12), `ai-proposals-page.component.ts` (7), `chats-page.component.html` (3). Rompen la coherencia visual, el responsive y el theming.
10. **Drift de Design System entre `app` y `landing`:**
    - Tipografía inconsistente: Landing carga `Manrope` vía `@import url(...)` bloqueante en `src/styles.css:1`; CRM declara `Inter` en `body` sin cargar la fuente (cae en fallback del SO).
    - `styles.css` duplicado (~336 líneas en cada repo) sin separación de tokens vs estilos base.
    - `shared/ui` mínimo (solo 2 componentes: `theme-toggle` y `legal-modal`), provocando CSS repetido en cada página para headers, tablas, cards de KPI, estados vacíos, alerts y modales.

### P2 — Medios (Calidad de código, reactividad, accesibilidad y seguridad)
11. **9 usos explícitos de `any` en dominio `agents`:** `agent-core.service.ts` (3), `agent-core.model.ts` (1), `business-context-page.component.ts` (5).
12. **Gestión de suscripciones RxJS inconsistente:** 76 `.subscribe()` en 22 archivos del CRM, pero solo 14 archivos usan `takeUntilDestroyed`/`DestroyRef`/`ngOnDestroy`; 13 `Subject`/`BehaviorSubject` usados para recargas manuales que pueden simplificarse con Signals o patrones consistentes con `DestroyRef`.
13. **Elemento clickeable no accesible en simulador (`business-context-page.component.html:334`):** `<div class="chat-bubble" (click)="selectMessage(msg)">` no es enfocable ni operable por teclado (`Enter`/`Space`).
14. **Tipografía y LCP en Landing (`styles.css:1`):** `@import url('https://fonts.googleapis.com/...')` dentro del CSS bloquea el renderizado inicial; debe moverse a `<link rel="preconnect">` + `<link rel="stylesheet">` en `index.html` (o fuente self-hosted) y aplicarse consistentemente en ambas apps.
15. **Manejo de errores HTTP duplicado:** Cada servicio/componente parsea `HttpErrorResponse` manualmente (`messageFromBackendError`, `toAuthError`, etc.) en lugar de un normalizador central en `core/utils/http-error.ts`.
16. **Endurecimiento de seguridad frontend:**
    - `token-storage.ts` guarda `access_token` y `refresh_token` en `localStorage` (documentado en `docs/SECURITY.md` por restricción de arquitectura actual); añadir manejo seguro ante excepciones de Storage (modo privado/cuota), limpieza estricta y revisar headers CSP/Nginx.
    - `ThemeService` accede a `localStorage` sin `try/catch` (puede fallar en navegadores con storage restringido).

### P3 — Bajos (Higiene y pulido)
17. **34 declaraciones redundantes de `standalone: true`** (29 CRM + 5 Landing).
18. **Indicador `notificationCount` hardcodeado en `0`** (`dashboard-shell.component.ts:45`) — conectar con el servicio real de notificaciones o documentar explícitamente su estado.
19. **Títulos y metadatos HTML duplicados entre `app/src/index.html` y `landing/src/index.html`:** Ambos tienen exactamente el mismo `<title>`, `<meta name="description">` y `<meta property="og:*">` de marketing; el CRM debería tener metadatos propios (`robots: noindex` para app privada y título propio).

---

## 7. Roadmap de Ejecución por Etapas

Cada etapa es independiente, incremental, entregable y verificable antes de pasar a la siguiente.

### Etapa 1 — Infraestructura Moderna Angular 21, Testing (Vitest) y Linting (Ambos frontends)
**Objetivo:** Establecer red de seguridad (tests unitarios + lint + builder moderno) y eliminar dependencias deprecadas sin cambiar comportamiento funcional.  
**Dependencias:** Ninguna (prerequisito de todas las etapas siguientes).  
**Tareas:**
- [x] Migrar builder de `@angular-devkit/build-angular` a `@angular/build` en `flowkron-front-app-angular` y `flowkron-front-landing-angular`.
- [x] Eliminar `@angular/animations` de ambos `package.json` y remover `provideAnimationsAsync()` de `flowkron-front-app-angular/src/app/app.config.ts`.
- [x] Configurar target `test` con **Vitest** (`@angular/build:unit-test`) y `tsconfig.spec.json` en ambas apps para que `npm test` ejecute limpio y rápido.
- [x] Configurar **ESLint** (`angular-eslint`, `@angular-eslint/template/accessibility`, reglas de boundaries y prohibición de `any`) en ambas apps con script `npm run lint`.
- [x] Crear specs unitarios base críticos:
  - CRM: `token-storage.spec.ts`, `theme.service.spec.ts`, `auth.interceptor.spec.ts`, `auth.guard.spec.ts`, `no-auth.guard.spec.ts`.
  - Landing: `theme.service.spec.ts`, `contact.service.spec.ts`, `legal-modal.component.spec.ts`, `landing-page.component.spec.ts`.
- [x] Actualizar `docs/TESTING.md` en ambos proyectos.

**Criterios de aceptación verificables:**
- `npm run build`, `npm test` y `npm run lint` pasan con código `0` en **ambas** apps.
- `0` referencias a `@angular/animations` en el workspace.
- Cobertura unitaria activa en `core/` (guards, interceptor, theme, storage) y formulario de contacto de Landing.

---

### Etapa 2 — Design System Unificado, Tokens CSS y Primitivos Atómicos (`shared/ui`)
**Objetivo:** Eliminar el drift visual entre `app` y `landing`, estructurar Design Tokens y construir la biblioteca atómica reutilizable con accesibilidad WCAG 2.2 AA nativa.  
**Dependencias:** Etapa 1.  
**Tareas:**
- [x] Crear `skills/frontend-design-system/SKILL.md` (o guía en `docs/DESIGN_SYSTEM.md` + skill) con estándares de tokens, tipografía, espaciado, estados y WCAG 2.2 AA.
- [x] Refactorizar `src/styles.css` en capas modulares (`src/styles/tokens.css`, `src/styles/reset.css`, `src/styles/primitives.css`) sincronizadas entre `app` y `landing`.
- [x] Unificar tipografía (`Manrope` / `Inter`) moviendo la carga fuera de `@import` bloqueante en CSS hacia `<link rel="preconnect">` en `index.html` (y diferenciar metadatos SEO/`noindex` entre Landing y CRM).
- [x] Unificar `LegalModalComponent` en CRM para usar `<dialog>` nativo + `input.required()` + `viewChild` (igual que Landing), eliminando el `<div (click)>` inaccesible.
- [x] Crear componentes atómicos/moleculares `OnPush` con Signal `input()`/`output()` en `flowkron-front-app-angular/src/app/shared/ui/`:
  - `fk-page-header` (`flowkron-page-header`: título, subtítulo, acciones)
  - `fk-stat-card` (`flowkron-stat-card`: KPI card con variante semántica)
  - `fk-badge` (`flowkron-badge`: variantes `primary`, `success`, `info`, `warning`, `danger`, `neutral`)
  - `fk-empty-state` (`flowkron-empty-state`: título, descripción, CTA opcional)
  - `fk-alert` (`flowkron-alert`: `role="alert"` / `role="status"`, variantes semánticas, dismiss opcional)
  - `fk-dialog` (`flowkron-dialog`: wrapper accesible sobre `<dialog>` nativo)
  - `fk-tabs` (`flowkron-tabs`: navegación por pestañas con `role="tablist"`, `aria-selected` y flechas de teclado)
- [x] Corregir bug de ícono faltante en `dashboard-shell.component.html` (`@case ('bell')` para `Propuestas IA`).
- [x] Escribir unit tests de todos los componentes de `shared/ui/` (incluyendo atributos ARIA y teclado).

**Criterios de aceptación verificables:**
- `styles/tokens.css` idéntico entre `app` y `landing`; misma tipografía y contraste WCAG 2.2 AA (≥ 4.5:1 texto normal, ≥ 3:1 texto grande/UI) en light y dark mode.
- `LegalModalComponent` en CRM usa `<dialog>` nativo, cierra con `Escape` y devuelve foco al disparador.
- `Propuestas IA` muestra su ícono en el sidebar.
- `npm run build`, `npm test` y `npm run lint` en verde en ambas apps.

---

### Etapa 3 — Eliminación de Inline Styles, Tipado Estricto y Descomposición de God Components (CRM)
**Objetivo:** Refactorizar las páginas pesadas e inconsistentes del CRM hacia la arquitectura Feature-Based + Presentational/Container, eliminando el warning de budget CSS y todos los `any` e inline styles.  
**Dependencias:** Etapa 2.  
**Tareas:**
- [x] **Refactorizar páginas con inline styles** para usar `shared/ui/` y hojas `.css` limpias (0 `style="..."` inline):
  - `opportunities-page` (extraer template/CSS + Reactive Form + `flowkron-page-header`, `flowkron-badge`, `flowkron-empty-state`, `flowkron-alert`)
  - `ai-proposals-page` (extraer template/CSS + `flowkron-page-header`, `flowkron-badge`, `flowkron-empty-state`, `flowkron-alert`)
  - `campaigns-page` (extraer template/CSS + Reactive Forms tipados + `switchMap` + `shared/ui`)
  - `chats-page` (migrar estilos inline de barra HITL y composer a `chats-page.component.css`)
- [x] **Descomponer `business-context-page`** (574 TS / 421 HTML / 733 CSS → budget de 11.94 kB eliminado):
  - Separado en 3 subcomponentes `OnPush` bajo `domains/agents/ui/`:
    - `context-summary-panel` (anillo de progreso, estado del agente, tabla de documentos)
    - `context-upload-panel` (carga de archivo, plantillas, asistente IA — migrado de `FormsModule`/`CommonModule` a `ReactiveFormsModule` tipado)
    - `agent-simulator-panel` (chat simulador + inspector RAG + `flowkron-dialog`; `<div (click)>` reemplazado por `<button type="button">` accesible)
  - Eliminados los 9 `any` en `agent-core.service.ts`, `agent-core.model.ts` y `business-context-page`.
- [x] Centralizar normalización de errores HTTP en `core/utils/http-error.ts` (+ `http-error.spec.ts`).
- [x] Promover `@typescript-eslint/no-explicit-any`, `click-events-have-key-events` e `interactive-supports-focus` a `error` en `eslint.config.mjs`.

**Criterios de aceptación verificables:**
- `0` warnings de budget CSS en `npm run build` (`business-context-page.component.css` < 4 kB).
- `0` ocurrencias de `any` explícito en todo `src/`.
- `0` ocurrencias de `style="..."` inline, `CommonModule` o `FormsModule` en todo `src/`.
- `0` elementos `<div (click)>` o `<span (click)>` sin semántica de botón/teclado.
- Unit tests cubriendo los nuevos subcomponentes y el normalizador de errores HTTP.

---

### Etapa 4 — Angular 21 Reactivo: `OnPush`, Signals-first y Migración a Zoneless
**Objetivo:** Llevar ambos frontends al modelo de rendimiento nativo de Angular 21 (`ChangeDetectionStrategy.OnPush` al 100% + `provideZonelessChangeDetection()` sin `zone.js`).  
**Dependencias:** Etapa 3.  
**Tareas:**
- [x] Eliminar `standalone: true` redundante en todos los componentes (0 ocurrencias en CRM y Landing).
- [x] Migrar el 100% de componentes (`42/42` CRM + `5/5` Landing) a `ChangeDetectionStrategy.OnPush`, convirtiendo el estado mutable restante en `analytics-page` y `landing-page` a `signal()`.
- [x] Configurar `changeDetection: "OnPush"` por defecto en schematics de ambos `angular.json`.
- [x] Activar `provideZonelessChangeDetection()` en `app.config.ts` de **ambas** apps.
- [x] Retirar `zone.js` de `polyfills` en `angular.json` y de `dependencies` en `package.json` de ambas apps.
- [x] Verificar reducción real del bundle inicial (`initial` en `ng build`).

**Criterios de aceptación verificables:**
- `100%` de componentes con `ChangeDetectionStrategy.OnPush`.
- `zone.js` completamente eliminado de `package.json` y `angular.json` en ambas apps.
- `npm run build`, `npm test` (en modo zoneless con `fixture.whenStable()`) y `npm run lint` pasan sin errores ni regresiones en ambas apps.
- Reducción medible en el tamaño del bundle inicial (documentada en este roadmap al cerrar la etapa).

---

### Etapa 5 — Pulido UX/UI, Microinteracciones, Responsive y Accesibilidad WCAG 2.2 AA
**Objetivo:** Elevar la experiencia visual y de interacción a estándar enterprise, garantizando cumplimiento verificable de WCAG 2.2 AA en light/dark mode y desktop/mobile.  
**Dependencias:** Etapa 4.  
**Tareas:**
- [x] **Jerarquía visual y microinteracciones:**
  - Transiciones sutiles (`@keyframes fk-fade-in`, `.btn:active`) respetando `@media (prefers-reduced-motion: reduce)` sincronizadas en `primitives.css` de ambas apps.
  - Skeleton loader reutilizable (`flowkron-skeleton`) integrado en `opportunities-page` y `ai-proposals-page` con anuncios `.sr-only`.
  - Sistema ligero de notificaciones toast (`ToastService` + `flowkron-toast-container` con `aria-live="polite"` y `role="alert"`/`role="status"`) montado en `dashboard-shell` y cubierto por `toast.service.spec.ts`.
- [x] **Resiliencia de tema y storage (CRM + Landing):**
  - `ThemeService` endurecido con `try/catch` en `localStorage` y sincronización automática de `meta[name="theme-color"]` (`#100d16` / `#f8f6fb`) cubierto por tests en ambas apps.
  - `token-storage.ts` endurecido con `try/catch` ante storage restringido o cuota excedida.
- [x] **Accesibilidad WCAG 2.2 AA:**
  - Templates auditados con `@angular-eslint/template/accessibility` en modo estricto (`0 errors, 0 warnings` en ambas apps), modales `<dialog>` nativos, tabs con navegación por flechas y `aria-live` en estados vacíos/toasts.

**Criterios de aceptación verificables:**
- `0` violaciones `critical` o `serious` en auditoría axe-core (light y dark mode) en Landing y vistas principales del CRM.
- Flujo completo navegable por teclado sin trampas de foco.
- `npm run build`, `npm test` y `npm run lint` en verde en ambas apps.

---

### Etapa 6 — Hardening de Producción, Performance, Seguridad y Documentación Final
**Objetivo:** Consolidar estándares de producción, CI/CD, seguridad frontend y documentación viva.  
**Dependencias:** Etapa 5.  
**Tareas:**
- [x] Añadir `npm test` y `npm run lint` de ambos frontends al workflow de GitHub Actions (`.github/workflows/validate.yml`).
- [x] Revisar `token-storage.ts` y `ThemeService` para resiliencia ante `localStorage` deshabilitado/restringido (completado en Etapa 5 y cubierto por specs).
- [x] Endurecer headers de seguridad Nginx (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-cache` en `/index.html` y `public, immutable` en assets hasheados) en ambos `nginx.conf`.
- [x] Validar `npm audit --omit=dev --audit-level=high` y `.github/scripts/check-dev-audit.mjs` en ambas apps.
- [x] Actualizar documentación de arquitectura (`docs/ARCHITECTURE.md`, `docs/TESTING.md`) en ambos repositorios reflejando el estado final.

**Criterios de aceptación verificables:**
- Pipeline CI ejecuta `lint` + `test` + `build` + `audit` para `flowkron-front-app-angular` y `flowkron-front-landing-angular` en verde.
- Documentación 100% alineada con el código real.

---

## 8. Registro de Seguimiento de Etapas

| Etapa | Descripción | Estado | Validaciones | Notas / Métricas |
|---|---|---|---|---|
| **Etapa 0** | Auditoría exhaustiva y diseño de Roadmap | **DONE** | Inspección estática + docs Angular 21 | 0 archivos de producción modificados. |
| **Etapa 1** | Builder `@angular/build`, Vitest, ESLint, retiro `@angular/animations` | **DONE** | `build` + `test` (18 CRM + 10 Landing) + `lint` (0 errors) + `audit --omit=dev` (0 vulns) | `-253` paquetes netos por app; corregidos 7 `<label for>` de a11y en onboarding y 2 errores TS en `auth.model.ts`. Baseline inicial: CRM `334.62 kB` (`96.15 kB` transfer), Landing `302.23 kB` (`82.85 kB` transfer). |
| **Etapa 2** | Design System unificado, Tokens CSS, `shared/ui` atómico, fix nav icon & modal | **DONE** | `build` + `test` (21 CRM + 10 Landing) + `lint` (0 errors) | `styles-NCKXYNRP.css` idéntico (`7.13 kB`) entre CRM y Landing (Landing bajó de `14.65 kB` CSS / `302.23 kB` → `294.71 kB`); warnings lint CRM bajaron 17 → 12; `@angular-eslint/no-output-native` promovido a `error`. |
| **Etapa 3** | Retiro inline styles, 0 `any`, descomposición `business-context` y refactor páginas CRM | **DONE** | `build` (0 warnings!) + `test` (25 CRM) + `lint` (**0 errors, 0 warnings**) | Inline styles `37 → 0`, `any` `9 → 0`, `FormsModule`/`CommonModule` `→ 0`, `<div (click)>` `2 → 0`; warning de budget CSS (`11.94 kB`) eliminado por completo. |
| **Etapa 4** | 100% `OnPush`, Signals-first y Zoneless (retiro `zone.js`) | **DONE** | `build` + `test` zoneless (25 CRM + 10 Landing) + `lint` (0 errors, 0 warnings) | `42/42` CRM + `5/5` Landing en `OnPush`, `0` `standalone: true`, `zone.js` eliminado. Bundle inicial: CRM `336.26 kB → 301.04 kB` (`95.95 → 84.53 kB` transfer, `-11.9%`), Landing `294.71 kB → 259.48 kB` (`82.75 → 71.31 kB` transfer, `-13.8%`). |
| **Etapa 5** | Pulido UI/UX, microinteracciones, skeletons/toasts y WCAG 2.2 AA | **DONE** | `build` + `test` (28 CRM + 11 Landing) + `lint` (0 errors, 0 warnings) | `flowkron-skeleton`, `ToastService`, `flowkron-toast-container`, `ThemeService` + `token-storage` resilientes con sync `meta[name="theme-color"]`; `styles-BUHQ5TGM.css` (`7.28 kB`) sincronizado en ambas apps. |
| **Etapa 6** | CI/CD, hardening Nginx/seguridad y documentación final | **DONE** | `lint` + `test` + `build` + `audit` + `check-dev-audit` en verde en ambas apps | `validate.yml` ejecuta `lint`, `test` y `build` en matrix; headers Nginx endurecidos (`nosniff`, `SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, `no-cache` en `index.html`); `docs/ARCHITECTURE.md` y `docs/TESTING.md` actualizados. |
