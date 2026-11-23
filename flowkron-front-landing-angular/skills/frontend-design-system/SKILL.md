---
name: frontend-design-system
description: Estándares de Design System, tokens CSS, componentes atómicos Angular 21 y accesibilidad WCAG 2.2 AA para Flowkron (app y landing).
---

# Flowkron Frontend Design System

## 1. Capas de Estilos y Tokens
- Todos los colores, tipografías, espaciados, radios, capas `z-index` y duraciones provienen de `src/styles/tokens.css` (sincronizado entre `flowkron-front-app-angular` y `flowkron-front-landing-angular`).
- Prohibido usar atributos `style="..."` inline en templates HTML y colores hexadecimales hardcodeados en componentes cuando exista un token semántico (`--primary`, `--foreground`, `--muted-foreground`, `--card`, `--border`, `--success-text`, `--error-text`, `--warning-text`, `--info-text`).
- Preservar soporte simultáneo de `:root` (claro) y `.dark` (oscuro), así como `@media (prefers-reduced-transparency: reduce)` y `@media (prefers-reduced-motion: reduce)`.

## 2. Componentes Atómicos (`src/app/shared/ui/`)
- Todos los primitivos UI deben usar `ChangeDetectionStrategy.OnPush`, `input()` / `input.required()`, `output()` y control flow nativo (`@if`, `@for`, `@switch`).
- Reutilizar los componentes de `shared/ui/` antes de crear marcado repetitivo:
  - `flowkron-page-header` (cabecera de página con eyebrow, título, subtítulo y slot de acciones)
  - `flowkron-stat-card` (KPI card con etiqueta, valor, detalle y tono semántico)
  - `flowkron-badge` (variantes `primary`, `success`, `info`, `warning`, `danger`, `neutral`)
  - `flowkron-empty-state` (estado vacío accesible con título, descripción y slot de acción)
  - `flowkron-alert` (banner `role="alert"` o `role="status"` con tono semántico)
  - `flowkron-dialog` (wrapper accesible sobre `<dialog>` nativo)
  - `flowkron-tabs` (`role="tablist"`, `aria-selected`, navegación con flechas)

## 3. Checklist WCAG 2.2 AA
1. Toda acción clickeable usa `<button type="button">` o `<a>`, nunca `<div (click)>` ni `<span (click)>`.
2. Todo `<input>`, `<select>` y `<textarea>` tiene `<label for="...">` asociado, `aria-invalid` y `aria-describedby` en estado de error.
3. Modales usan `<dialog>` nativo (`showModal()`), cierran con `Escape` y mantienen el foco visible (`:focus-visible`).
4. Contraste mínimo 4.5:1 en texto normal y 3:1 en texto grande o controles interactivos en ambos temas (claro y oscuro).
5. Tamaños interactivos mínimos de `40x40px` en controles táctiles/navegación.
