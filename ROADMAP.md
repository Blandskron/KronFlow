# KronFlow — Intelligent CRM: Rebranding, Design System & Frontend Architecture Roadmap

> **Fecha de auditoría:** 2026-11-25  
> **Producto:** **KronFlow — Intelligent CRM** (`Smart conversations. Seamless automation.`)  
> **Ecosistema:** Open Source · **By BLANDSKRON**  
> **Referencia de ADN visual:** [`https://blandskron.cl/`](https://blandskron.cl/)  
> **Skill incorporada:** [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) → `.agents/skills/ui-ux-pro-max/` (auditada y verificada)

---

## 1. Resumen Ejecutivo de Auditoría y Diagnóstico

### 1.1 Estado Actual del Frontend (Pre-Rebranding)
Ambos frontends (`flowkron-front-app-angular` y `flowkron-front-landing-angular`) cuentan con una base técnica moderna (**Angular 21.2.26 Zoneless**, `100% OnPush`, **Vitest**, **ESLint** con `@angular-eslint/template/accessibility`), pero presentan brechas críticas de marca, identidad visual, consistencia de tokens y UX:

| Dimensión | Estado actual auditado | Impacto / Brecha |
|---|---|---|
| **Identidad y Marca** | Nombre **Flowkron**, paleta violeta `#4A148C` / `#2E0B59`, tipografía única `Manrope` (sin display/body pairing) | No representa comunicación inteligente, flujo ni automatización; choca con la identidad diferenciada de producto dentro de BLANDSKRON. |
| **Selectores y Metadatos** | `134` referencias a selectores `flowkron-*` en CRM y `11` en Landing; `index.html`, `manifest.webmanifest`, `angular.json`, `eslint.config.mjs` y `smoke.py` acoplados a `Flowkron`. | Requiere renombrado integral coordinado en componentes, templates, specs, manifests y CI smoke tests. |
| **Colores hardcodeados / Drift de tokens** | **30 ocurrencias** de hex/rgba hardcodeados fuera de `tokens.css` en CRM (`auth-layout`, `workflows-page`, `settings-page`, `confirm-email-page`, `dialog`, `legal-modal`, `primitives.css`, `theme.service.ts`) y **10** en Landing (`#13784d`, `#100d16`, `#f8f6fb`, `rgba(15, 7, 23, 0.68)`, `rgba(126, 65, 188, ...)`). | Impide evolucionar el tema de manera centralizada y rompe la coherencia entre light/dark mode y scrims de modales. |
| **Navegación Sidebar CRM** | `dashboard-shell.component.ts` reutiliza `icon: 'link'` tanto para **WhatsApp** como para **Campañas** (`@case ('link')`). | Ambigüedad visual entre dos módulos distintos en la navegación principal. |
| **Dock móvil CRM (`<= 820px`)** | `.sidebar nav` usa `grid-template-columns: repeat(4, minmax(0, 1fr))` con 9 ítems (3 filas apiladas en el fondo de la pantalla). | Barra inferior excesivamente alta en móvil que reduce el área útil de lectura en bandejas y tablas. |
| **Landing & Showcase (`index.html`)** | Landing Angular usa layout básico de 4 cards planas sin jerarquía técnica ni diagrama de arquitectura; `index.html` raíz aún porta marca y paleta Flowkron violeta. | No refleja el nivel arquitectónico de `blandskron.cl` ni comunica la arquitectura RAG + HITL + Multi-tenant. |
| **Recursos SVG (`assets/brand/`)** | 5 SVGs básicos en violeta `#4A148C` (`flowkron-*.svg`), sin variante monocroma, sin OG card `1200×630` y sin diagrama arquitectónico SVG. | Kit de marca incompleto para repositorio open source, redes, favicons y UI. |

---

### 1.2 Auditoría del ADN Visual de BLANDSKRON (`https://blandskron.cl/`)
Inspección en navegador real (`1440×900` y `364×601`, dark y light mode) sobre la hoja de estilos compilada y DOM vivo de `https://blandskron.cl/`:
- **Dark-first arquitectónico:** `color-scheme: dark` por defecto, canvas obsidiana profundo, superficies estratificadas con bordes hairline luminosos y retícula ortogonal de `86px × 86px` con máscara vertical suave.
- **Floating Glassmorphism:** Header flotante tipo pill (`.glass-header`) centrado con `backdrop-filter: blur(...)`, borde superior sutil (`inset 0 1px`), radios generosos (`21px–24px` en cards, `11px–12px` en controles) y elevaciones limpias.
- **Tipografía & Kickers Técnicos:** Pairing Display + Body + Monospace (`--mono` en eyebrows con prefijo `01 / ...`, badges pill y métricas con `tabular-nums`), tracking ajustado en headings (`-0.04em` a `-0.06em`).
- **Bento Grids y Diagramas Orbitales/de Flujo:** Secciones con grillas asimétricas de 12 columnas (`span 7 / span 5`) y diagramas vectoriales de núcleo + nodos conectados.

**Evolución para KronFlow:** Conservamos exactamente este ADN estructural de BLANDSKRON (dark mode por defecto, retícula sutil, floating glassmorphism, kickers monospace, Bento grids y diagramas de flujo), pero construyendo una **identidad propia** basada en **Teal (`#0D9488` / `#2DD4BF`), Verde Esmeralda (`#10B981` / `#34D399`) y Cyan (`#06B6D4` / `#38BDF8`)**, con tipografía **Sora** (display), **Inter** (UI/cuerpo) y **JetBrains Mono** (kickers/métricas/código).

---

### 1.3 Evaluación e Incorporación de Skill `UI/UX Pro Max`
- **Origen:** [`nextlevelbuilder/ui-ux-pro-max-skill`](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (Licencia **MIT**).
- **Revisión de seguridad previa:** Se auditaron `SKILL.md` y todos los scripts Python (`core.py`, `search.py`, `design_system.py`, `preview.py`, `reasoning_contract.py`). Utilizan exclusivamente biblioteca estándar de Python (`csv`, `json`, `pathlib`, `re`, `math`, `argparse`), sin llamadas de red, sin `subprocess`, sin `eval`/`exec` y sin escritura fuera de archivos solicitados explícitamente.
- **Integración:** Instalada en `.agents/skills/ui-ux-pro-max/` (48 archivos) y verificada en Python `3.13.14` (`--design-system`, `--domain ux`, `--stack angular`, `--domain style`).

---

### 1.4 Decisión de Arquitectura: Preservación de Infraestructura
Para garantizar **cero regresiones** en Docker, Nginx, CI/CD (`.github/workflows/validate.yml`), redes internas de Compose y contratos entre microservicios:
- **Se renombra integralmente** toda la marca visible, SVGs, favicons, tokens, selectores Angular (`flowkron-*` → `kronflow-*`), prefijos ESLint/Angular, metadatos HTML/PWA, README, documentación y verificaciones de smoke test (`smoke.py`).
- **Se conservan intactos** los nombres históricos de directorios raíz (`flowkron-front-app-angular`, `flowkron-front-landing-angular`, `flowkron-auth-service`, `flowkron-operational-service`, `flowkron-agent-core`, `flowkron-mail-service`, `flowkron-baileys-services`, `flowkron-api-contracts`, `flowkron-deploy`), nombres de servicios Docker/Compose y `outputPath` (`dist/flowkron-front-*-angular`) para no romper `Dockerfile`, `compose*.yaml` ni pipelines existentes.

---

## 2. Identidad Visual de KronFlow — Intelligent CRM

- **Nombre oficial:** `KronFlow` · `KronFlow — Intelligent CRM`
- **Tagline:** `Smart conversations. Seamless automation.`
- **Atribución:** `Open Source · By BLANDSKRON`
- **Concepto del isotipo ("Conversational Intelligence Nexus"):** Squircle oscuro obsidiana-teal (`rx="18"`, gradiente `#07161B → #0B252C`, borde `#2DD4BF33`) con un monograma geométrico **K + trayectoria conversacional** en gradiente Teal → Esmeralda → Cyan (`#2DD4BF → #10B981 → #06B6D4`) y 3 nodos de automatización inteligente conectados.
- **Tipografía:** `Sora` (Display / Headings) + `Inter` (UI / Body) + `JetBrains Mono` (Eyebrows / Badges técnicos / Tabular data / Código).
- **Paleta núcleo:**
  - Dark default (`#060D10` canvas, `#0B161B` surface, `#EEF7F6` text, `#2DD4BF` primary, `#0F766E → #047857` CTA gradient)
  - Light (`#F1F8F7` canvas, `#FFFFFF` surface, `#091E24` text, `#0F766E` / `#115E59` primary)

---

## 3. Plan de Ejecución por Etapas y Criterios de Aceptación

### Etapa 0 — Incorporación de Skill `UI/UX Pro Max` y Creación de `ROADMAP.md`
- **Estado:** `DONE`
- **Tareas:**
  - [x] Auditar seguridad y licencia (MIT) de `nextlevelbuilder/ui-ux-pro-max-skill`.
  - [x] Instalar `.agents/skills/ui-ux-pro-max/` (48 archivos) y adaptar rutas en `SKILL.md`.
  - [x] Verificar scripts con Python 3.13 (`search.py --design-system`, `--domain ux`, `--stack angular`, `--domain style`).
  - [x] Crear `ROADMAP.md` en la raíz del proyecto.
- **Criterios de aceptación:**
  - `python .agents/skills/ui-ux-pro-max/scripts/search.py` responde con exit code `0`.
  - `ROADMAP.md` documenta auditoría, ADN visual, arquitectura de marca y etapas verificables.

### Etapa 1 — Identidad Visual Original y Kit de Recursos SVG (`assets/brand/`)
- **Estado:** `DONE`
- **Dependencias:** Etapa 0.
- **Tareas:**
  - [x] Diseñar `kronflow-icon.svg` (`72×72`) y `kronflow-icon-monochrome.svg` (`currentColor`).
  - [x] Diseñar lockups horizontales (`kronflow-horizontal-dark.svg`, `kronflow-horizontal-light.svg`) y apilados (`kronflow-stacked-dark.svg`, `kronflow-stacked-light.svg`).
  - [x] Diseñar `kronflow-og-card.svg` (`1200×630`) y `kronflow-hero-flow.svg` (diagrama arquitectónico SVG de orquestación IA).
  - [x] Retirar `assets/brand/flowkron-*.svg` y actualizar `assets/brand/README.md`.
  - [x] Publicar `kronflow-icon.svg` en `flowkron-front-app-angular/public/` y `flowkron-front-landing-angular/public/`, eliminando `flowkron-icon.svg`.
- **Criterios de aceptación:**
  - 8 archivos SVG válidos en `assets/brand/` sin referencias a `#4A148C` ni texto `Flowkron`.
  - `0` archivos `flowkron-icon.svg` en `public/` de ambos frontends.

### Etapa 2 — Design System Unificado (`tokens.css`, `reset.css`, `primitives.css`, `ThemeService`)
- **Estado:** `DONE`
- **Dependencias:** Etapa 1.
- **Tareas:**
  - [x] Unificar `src/styles/tokens.css`, `reset.css` y `primitives.css` entre `flowkron-front-app-angular` y `flowkron-front-landing-angular` con paleta Teal/Esmeralda/Cyan, `Sora` + `Inter` + `JetBrains Mono`, retícula arquitectónica (`--grid-ink`) y tokens semánticos completos (`--backdrop-scrim`, `--primary-glow`, `--focus-ring`, `--primary-strong`).
  - [x] Actualizar `ThemeService` (`#060d10` / `#f1f8f7`) y sus specs unitarios en ambas apps.
  - [x] Actualizar `skills/frontend-design-system/SKILL.md` en ambas apps.
- **Criterios de aceptación:**
  - `tokens.css`, `reset.css` y `primitives.css` idénticos byte-a-byte entre CRM y Landing.
  - `0` referencias a `--ambient-violet`, `--brand-purple` o `flowkron-icon.svg` en `src/styles/`.

### Etapa 3 — Renombrado Integral y Perfeccionamiento UX/UI del CRM (`flowkron-front-app-angular`)
- **Estado:** `DONE`
- **Dependencias:** Etapa 2.
- **Tareas:**
  - [x] Renombrar `prefix` en `angular.json` y `eslint.config.mjs` a `kronflow`; actualizar `src/index.html` (Google Fonts `Sora` + `Inter` + `JetBrains Mono`, `kronflow-icon.svg`, `<kronflow-root>`) y `public/manifest.webmanifest`.
  - [x] Migrar todos los selectores `flowkron-*` → `kronflow-*` y textos de marca `Flowkron` → `KronFlow` en `src/app/**`.
  - [x] Rediseñar `auth-layout` con identidad obsidiana-teal/cyan, retícula sutil y copy oficial (`Smart conversations. Seamless automation.`).
  - [x] Corregir íconos de `dashboard-shell` (`LucideSmartphone` WhatsApp, `LucideMegaphone` Campañas, `LucideSparkles` Propuestas IA), mejorar estados activos, corregir WCAG 2.5.3 en botón `Salir` y transformar el dock móvil (`<=820px`) en fila horizontal deslizable de una sola línea.
  - [x] Pulir `home-page`, `.page-section` / `.context-container`, `shared/ui/*` y eliminar los colores violetas/hardcodeados en `workflows-page`, `settings-page`, `confirm-email-page`, `agent-simulator-panel` y `context-upload-panel`.
- **Criterios de aceptación:**
  - `0` ocurrencias de `<flowkron-` o `selector: 'flowkron-` en `flowkron-front-app-angular/src/`.
  - `0` colores violetas hardcodeados (`rgba(126, 65, 188...)`, `#4A148C`, `#100d16`, `#f8f6fb`, `rgba(15, 7, 23...)`).
  - `npm run lint`, `npm test` y `npm run build` pasan con código `0` y `0` warnings.

### Etapa 4 — Rediseño Integral de Landing (`flowkron-front-landing-angular`) y Showcase (`index.html`)
- **Estado:** `DONE`
- **Dependencias:** Etapa 2.
- **Tareas:**
  - [x] Renombrar `prefix` a `kronflow` en `angular.json` y `eslint.config.mjs`; actualizar `src/index.html`, `manifest.webmanifest`, selectores `kronflow-*` y copy legal.
  - [x] Rediseñar `landing-page` heredando el ADN de `blandskron.cl` (header flotante pill, hero `Smart conversations. Seamless automation.` con preview conversacional glass + indicadores RAG/HITL, Bento Grid de 4 módulos numerados `01–04`, tira de arquitectura Open Source, formulario de contacto accesible intacto y footer oficial).
  - [x] Actualizar `landing-page.component.spec.ts`, `legal-modal.component.spec.ts` y `tests/visual/kronflow-landing.visual.spec.ts`.
  - [x] Rediseñar `index.html` raíz con la nueva identidad KronFlow (`Sora` + `Inter` + `JetBrains Mono`, Teal/Emerald/Cyan, SVG brand kit).
- **Criterios de aceptación:**
  - `npm run lint`, `npm test` y `npm run build` en `flowkron-front-landing-angular` pasan con código `0` y `0` warnings.
  - Formulario de contacto conserva todos sus atributos ARIA, IDs y flujo CSRF intactos.

### Etapa 5 — Documentación, READMEs, Metadatos y Smoke Test CI
- **Estado:** `DONE`
- **Dependencias:** Etapas 3 y 4.
- **Tareas:**
  - [x] Actualizar `README.md` raíz con el nuevo branding KronFlow, logo SVG adaptable light/dark y guía operativa.
  - [x] Actualizar `ARCHITECTURE.md`, `CONTRIBUTING.md`, `NOTICE`, `RELEASE_READINESS.md`, `THIRD_PARTY.md`, `CHANGELOG.md`, `docs/IMPLEMENTATION_STATUS.md` y plantillas `.github/`.
  - [x] Actualizar READMEs, `docs/*` y `AGENTS.md` en `flowkron-front-app-angular` y `flowkron-front-landing-angular`.
  - [x] Actualizar `flowkron-deploy/bootstrap/smoke.py` para validar `"KronFlow"` en Landing y CRM `/login`.
- **Criterios de aceptación:**
  - Consistencia total de marca `KronFlow — Intelligent CRM` en READMEs, metadatos, plantillas y `smoke.py`.

### Etapa 6 — Validación Integral (Playwright, Capturas, WCAG 2.2 AA y Lighthouse)
- **Estado:** `DONE`
- **Dependencias:** Etapas 3, 4 y 5.
- **Tareas:**
  - [x] Ejecutar suite completa (`lint`, `test`, `build`, `npm audit --omit=dev --audit-level=high`) en ambos frontends.
  - [x] Servir builds de producción (`Landing` y `CRM`) y validar con Playwright en desktop (`1440×900`) y móvil (`390×844`), dark y light mode: navegación, contraste, teclado, `<dialog>` modal (`Escape`), `0` errores de consola y `0` overflow horizontal.
  - [x] Ejecutar auditoría `axe-core` WCAG 2.2 AA en Landing (dark/light, desktop/mobile) y vistas del CRM (`login`, `home`, `contacts`, `opportunities`, `business-context`, `ai-simulator`, `campaigns`, `analytics`, `conversations`).
  - [x] Capturar y verificar visualmente las 10 capturas en `docs/screenshots/01..10-*.png`.
  - [x] Ejecutar Lighthouse (Performance, Accessibility, Best Practices, SEO) y documentar resultados reales en este `ROADMAP.md`.
- **Criterios de aceptación:**
  - `0` violaciones `critical`, `serious` o `minor` en 15 auditorías `axe-core` WCAG 2.2 AA.
  - Lighthouse Landing: Performance `98`, Accessibility `100`, Best Practices `100`, SEO `91`.
  - Lighthouse CRM Login: Performance `100`, Accessibility `100`, Best Practices `96` (`SEO 54` intencional por `<meta name="robots" content="noindex, nofollow">`).
  - Todas las capturas en `docs/screenshots/` actualizadas e inspeccionadas sin defectos visuales.

---

## 4. Registro de Seguimiento de Etapas

| Etapa | Descripción | Estado | Validaciones | Métricas / Notas |
|---|---|---|---|---|
| **Etapa 0** | Auditoría completa, skill `ui-ux-pro-max` y `ROADMAP.md` | **DONE** | `search.py` CLI verificado en Python 3.13 | 48 archivos de skill instalados en `.agents/skills/ui-ux-pro-max/`. |
| **Etapa 1** | Identidad visual original y kit SVG en `assets/brand/` | **DONE** | 8 SVGs válidos + `kronflow-icon.svg` en ambos `public/` | 0 archivos `flowkron-*.svg` remanentes. |
| **Etapa 2** | Design System unificado (`tokens`, `reset`, `primitives`, `ThemeService`) | **DONE** | `tokens.css`, `reset.css` y `primitives.css` sincronizados byte-a-byte | Paleta Teal/Esmeralda/Cyan, `Sora` + `Inter` + `JetBrains Mono`, `styles-*.css` = `9.61 kB` (`2.64 kB` transfer) en ambas apps. |
| **Etapa 3** | Renombrado y pulido UX/UI de CRM (`flowkron-front-app-angular`) | **DONE** | `lint` (0/0) + `test` (28/28) + `build` (`302.91 kB` initial) + `audit` (0 vulns) | 0 selectores `flowkron-*`, 0 colores violetas, WCAG 2.5.3 corregido en `Salir`, padding `.page-section` unificado. |
| **Etapa 4** | Rediseño de Landing (`flowkron-front-landing-angular`) y `index.html` | **DONE** | `lint` (0/0) + `test` (11/11) + `build` (`262.22 kB` initial) + `audit` (0 vulns) | Bento Grid `01–04`, preview IA/RAG, `contactForm` CSRF preservado, `index.html` actualizado. |
| **Etapa 5** | READMEs, documentación, metadatos y `smoke.py` | **DONE** | Revisión transversal y `git grep` | `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `NOTICE`, `smoke.py` y docs de frontends actualizados. |
| **Etapa 6** | Validación Playwright, capturas, WCAG 2.2 AA y Lighthouse | **DONE** | 15 auditorías `axe-core` WCAG 2.2 AA (`0` violaciones, `0` overflow, `0` console errors) + Lighthouse + inspección visual | Landing LH: `98/100/100/91`; CRM Login LH: `100/100/96/54` (`noindex`); `docs/screenshots/01..10-*.png` actualizadas. |
