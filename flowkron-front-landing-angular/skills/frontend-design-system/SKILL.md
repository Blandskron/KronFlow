---
name: frontend-design-system
description: Estándares de Design System, tokens CSS Teal/Esmeralda/Cyan, tipografía Sora/Inter/JetBrains Mono, Floating Glassmorphism, componentes atómicos Angular 21 y accesibilidad WCAG 2.2 AA para KronFlow (app y landing).
---

# KronFlow Frontend Design System

**KronFlow — Intelligent CRM** · *Smart conversations. Seamless automation.* · Open Source · By **BLANDSKRON**

## 1. Capas de Estilos y Tokens
- Todos los colores, tipografías, espaciados, radios, capas `z-index`, retícula (`--grid-ink`) y duraciones provienen de `src/styles/tokens.css` (idéntico entre `flowkron-front-app-angular` y `flowkron-front-landing-angular`).
- Tipografía oficial: `--font-display` (`Sora`) para encabezados (`h1–h4`), `--font-sans` (`Inter`) para interfaz y cuerpo, `--font-mono` (`JetBrains Mono`) para `.eyebrow`, métricas y código.
- Prohibido usar atributos `style="..."` inline en templates HTML y colores hexadecimales/rgba hardcodeados en componentes cuando exista un token semántico (`--primary`, `--primary-strong`, `--foreground`, `--muted-foreground`, `--card`, `--border`, `--backdrop-scrim`, `--primary-glow`, `--focus-ring`, `--success-text`, `--error-text`, `--warning-text`, `--info-text`).
- Preservar soporte simultáneo de `.dark` (oscuro por defecto `#060d10`) y `:root` (claro `#f1f8f7`), así como `@media (prefers-reduced-transparency: reduce)` y `@media (prefers-reduced-motion: reduce)`.

## 2. Componentes Atómicos (`src/app/shared/ui/`)
- Todos los primitivos UI deben usar `ChangeDetectionStrategy.OnPush`, `input()` / `input.required()`, `output()` y control flow nativo (`@if`, `@for`, `@switch`).
- Prefijo oficial de selectores: `kronflow-*`.
- Reutilizar los componentes de `shared/ui/` antes de crear marcado repetitivo:
  - `kronflow-theme-toggle`
  - `kronflow-legal-modal` (wrapper accesible sobre `<dialog>` nativo con `--backdrop-scrim`)

## 3. Checklist WCAG 2.2 AA
1. Toda acción clickeable usa `<button type="button">` o `<a>`, nunca `<div (click)>` ni `<span (click)>`.
2. Todo `<input>`, `<select>` y `<textarea>` tiene `<label for="...">` asociado, `aria-invalid` y `aria-describedby` en estado de error.
3. Modales usan `<dialog>` nativo (`showModal()`), cierran con `Escape` y mantienen el foco visible (`:focus-visible`).
4. Contraste mínimo 4.5:1 en texto normal y 3:1 en texto grande o controles interactivos en ambos temas (claro y oscuro).
5. Tamaños interactivos mínimos de `40x40px` en controles táctiles/navegación.
