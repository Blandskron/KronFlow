# KronFlow Brand Assets

**KronFlow — Intelligent CRM** — *Smart conversations. Seamless automation.* — Open Source · By **BLANDSKRON**

---

## 1. Concepto del Isotipo ("Conversational Intelligence Nexus")

El isotipo de KronFlow combina:
- **Contenedor arquitectónico obsidiana-teal** (`rx="18"`), heredado de la estética técnica de BLANDSKRON.
- **Columna vertebral vertical (`K`)**, que simboliza estabilidad, gobernanza multi-tenant y trazabilidad.
- **Trayectoria conversacional fluida** en gradiente Teal → Verde Esmeralda → Cyan, conectando 3 nodos de automatización inteligente (ingreso conversacional, núcleo RAG/HITL y ejecución en pipeline).

---

## 2. Archivos Incluidos

| Archivo | Uso recomendado |
|---|---|
| [`kronflow-icon.svg`](kronflow-icon.svg) | Favicon (`16×16`–`64×64`), app icon, PWA manifest y sidebar del CRM |
| [`kronflow-icon-monochrome.svg`](kronflow-icon-monochrome.svg) | Watermarks, badges monocromos e íconos con herencia `currentColor` |
| [`kronflow-horizontal-dark.svg`](kronflow-horizontal-dark.svg) | Headers, README y documentación sobre fondos oscuros |
| [`kronflow-horizontal-light.svg`](kronflow-horizontal-light.svg) | Headers y documentación sobre fondos claros |
| [`kronflow-stacked-dark.svg`](kronflow-stacked-dark.svg) | Portadas, presentaciones y vistas centradas sobre fondos oscuros |
| [`kronflow-stacked-light.svg`](kronflow-stacked-light.svg) | Portadas y vistas centradas sobre fondos claros |
| [`kronflow-og-card.svg`](kronflow-og-card.svg) | Tarjeta Open Graph (`1200×630`) y previsualización social |
| [`kronflow-hero-flow.svg`](kronflow-hero-flow.svg) | Diagrama arquitectónico SVG de orquestación conversacional |

Las copias en `frontend/app/public/kronflow-icon.svg` y `frontend/landing/public/kronflow-icon.svg` reflejan exactamente `kronflow-icon.svg` (junto con `frontend/landing/public/kronflow-og-card.svg` para metadatos sociales) para que cada aplicación compile de forma independiente.

---

## 3. Paleta de Color Oficial

| Token | Dark (Default) | Light | Uso |
|---|---|---|---|
| Canvas (`--background`) | `#060D10` | `#F1F8F7` | Fondo principal |
| Surface (`--card`) | `#0B161B` | `#FFFFFF` | Tarjetas y paneles glass |
| Primary (`--primary`) | `#2DD4BF` | `#0F766E` | Acento principal e interacciones |
| Emerald (`--brand-emerald`) | `#10B981` | `#059669` | Estados activos, éxito y automatización |
| Cyan (`--brand-cyan`) | `#06B6D4` | `#0284C7` | Flujo conversacional e información |
| Ink (`--foreground`) | `#EEF7F6` | `#091E24` | Texto principal |
| Muted (`--muted-foreground`) | `#94B4BC` | `#3B5860` | Texto secundario |

---

## 4. Tipografía

- **Display / Títulos:** `Sora` (pesos `500`, `600`, `700`, `800`)
- **Interfaz / Cuerpo:** `Inter` (pesos `400`, `500`, `600`, `700`)
- **Kickers / Métricas / Código:** `JetBrains Mono` (pesos `400`, `500`, `600`)

---

## 5. Reglas de Uso

1. Mantener un margen de seguridad (*clearspace*) mínimo equivalente al `25%` del ancho del isotipo alrededor de cualquier lockup.
2. No distorsionar proporciones, no rotar el isotipo ni reemplazar el gradiente oficial por colores fuera de la paleta Teal/Esmeralda/Cyan.
3. Usar `kronflow-horizontal-dark.svg` sobre fondos oscuros (`#060D10`–`#102027`) y `kronflow-horizontal-light.svg` sobre fondos claros (`#F1F8F7`–`#FFFFFF`).
