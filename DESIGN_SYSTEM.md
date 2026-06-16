# Design System — Parapegma ("Flow")

Aesthetic target: **modern-classic, Cohere-adjacent** — a calm, editorial, high-craft
interface. Generous whitespace, a quiet cool-neutral canvas, restrained use of saturated
color (color is earned, not sprayed), crisp hairline borders, soft low-opacity shadows, and
confident-but-not-loud typography. Color is delivered entirely through the token layer in
[web/src/index.css](web/src/index.css); component code never names a hex value.

---

## 1. Palette and semantic mapping

Five raw scales (50–950) are declared as `--color-<scale>-<step>` theme variables. Semantic
tokens alias onto them. The five scales split cleanly into **one neutral backbone** and
**four saturated brand/state hues**.

| Scale | Character | Semantic role |
| --- | --- | --- |
| **blue-slate** | low-saturation cool gray-blue | **Neutral backbone** — backgrounds, surfaces, body/muted/subtle text, borders, dividers |
| **lavender** | saturated blue-violet | **Primary / brand** — buttons, links, active nav, focus ring, brand accents |
| **powder-blue** | saturated azure (close kin of lavender) | **Info** — informational badges/alerts (used sparingly precisely because it is close to primary) |
| **granite** | muted teal-green | **Secondary accent** — the calm counter-hue to primary (e.g. condition B, decorative accents) |
| **evergreen** | true green | **Success** — confirmations, "active" status, condition D |

### The warm-hue problem (deliberate, documented exception)

All five supplied scales are **cool**. There is no hue that can honestly carry *caution*
(amber) or *destruction* (red) without colliding with success-green or primary-blue. Using a
cool color for a destructive "Delete passkey" button would be a usability defect, not a style
choice. We therefore add **two functional-only colors** — `--color-warning` (amber) and
`--color-danger` (red) — tuned to sit calmly beside the cool palette (slightly desaturated,
not candy-bright). They are **not** part of the brand scales and are used only for status
semantics. This is the one place we intentionally step outside the supplied palette, and it
is the right call.

### Semantic token resolution

| Token | Light | Dark | Notes |
| --- | --- | --- | --- |
| `primary` | `lavender-600` `#345498` | `lavender-400` `#6787cb` | fill **and** link text |
| `primary-hover` | `lavender-700` | `lavender-300` | |
| `primary-dark` | `lavender-700` | `lavender-300` | text on a `primary/10` tint |
| `on-primary` / `primary-foreground` | `#ffffff` | `blue-slate-950` `#0e1315` | **dark mode flips to dark text** on the lighter dark-mode primary fill so contrast holds |
| `accent` | `granite-600` `#4f7d6f` | `granite-300` `#a1c4b9` | secondary brand accent |
| `bg` | `blue-slate-50` `#f0f3f5` | `blue-slate-950` `#0e1315` | app canvas |
| `surface` | `#ffffff` | `blue-slate-900` `#151b1e` | cards |
| `surface-2` | `blue-slate-50` | `blue-slate-800` | raised/hover |
| `surface-3` / `surface-muted` / `surface-hover` | `blue-slate-100` `#e1e7ea` | `blue-slate-800` `#29363d` | |
| `surface-alt` | `blue-slate-50` | `blue-slate-800` | |
| `text` | `blue-slate-950` `#0e1315` | `blue-slate-50` `#f0f3f5` | body |
| `text-muted` | `blue-slate-600` `#536c79` | `blue-slate-300` `#a4b7c1` | secondary text |
| `text-subtle` | `blue-slate-500` `#678898` | `blue-slate-400` `#869fac` | timestamps / non-essential only (≥3:1) |
| `border` | `blue-slate-200` `#c2cfd6` | `blue-slate-700` `#3e515b` | hairlines |
| `divider` | `blue-slate-100` `#e1e7ea` | `blue-slate-800` `#29363d` | |
| `success` | `evergreen-700` `#456831` | `evergreen-400` `#8fbe74` | text on `success/10` tint |
| `warning` | `#97651b` (amber) | `#d9a64a` | functional exception |
| `danger` / `error` | `#c2453d` (red) | `#e06b62` | works as solid fill *and* tint text |
| `danger-hover` | `#a23a33` | `#c2453d` | |
| `info` | `powder-blue-600` `#375e95` | `powder-blue-300` `#8fadd6` | |
| `accent` | `granite-600` | `granite-300` | |
| `chat-bg` | `blue-slate-50` | `blue-slate-950` | replaces the old WhatsApp beige for a cleaner editorial canvas |
| `bubble-in` (assistant) | `#ffffff` | `blue-slate-800` | white card on light |
| `bubble-out` (user) | `lavender-100` `#d9e1f2` | `lavender-800` `#1a2a4c` | soft brand tint |
| `bubble-system` | `blue-slate-100` | `blue-slate-800` | |
| `focus` | `lavender-500` @ 40% | `lavender-400` @ 45% | focus ring |

---

## 2. Light & dark mode

Both modes are supported (the app already ships a `light`/`dark`/`system` switch). Dark mode
is **not** a mechanical inversion: the 50–200 surface steps flip to the 800–950 steps, text
flips from 950→50, and the **saturated hues lighten by ~200 steps** (e.g. primary
`lavender-600`→`lavender-400`, success `evergreen-700`→`evergreen-400`) so they keep contrast
against the dark surface. The one structural flip is `on-primary`: white on the dark, deep
primary fill in light → near-black on the lighter primary fill in dark. Values were chosen by
eye + contrast math, not by formula (see §5).

---

## 3. Typography

- **Font:** humanist sans, system-first for a fast, offline-friendly PWA (no web-font
  network dependency). Stack favors Inter when locally available, then the platform UI sans:
  `"Inter", "Inter var", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue",
  Arial, sans-serif`. This reads modern and quietly professional — the right register for a
  cool, muted, research-grade product, where a geometric/playful face would feel off.
- **Display tracking:** headings get a hair of negative letter-spacing (`-0.011em`) and tight
  leading for the "classic" editorial feel; body stays at normal tracking with relaxed
  leading for readability.
- **Scale:** Major Third, ratio **1.25**, 16px base. Steps (rounded to the px the app already
  uses): 12 · 13 · 14 · 16 (base) · 18 · 20 · 24 · 30 · 36 · 48. The existing arbitrary sizes
  (`text-[15px]`, `text-[17px]`) are retained where they tune chat density; they sit inside
  this scale's intent and are not worth churning every call site.
- **Weights:** 400 body, 500 medium for controls/labels, 600 semibold for headings. We avoid
  700+ except the landing display, matching the restrained Cohere tone.

---

## 4. Spacing, radius, shadow, motion

- **Spacing:** Tailwind's default 4px scale, unmodified.
- **Radius:** existing tokens retained (`sm 10 / md 14 / lg 18 / pill 999`). They already read
  "soft modern"; left intact to avoid pointless layout churn.
- **Shadow:** soft, low-opacity (`sm`, `md`) — kept deliberately light so cards read as
  paper-on-canvas rather than floating chrome.
- **Motion:** `transition-colors` on interactive states only; no decorative animation. Calm.

---

## 5. Accessibility / WCAG contrast pass

Checked against the **rendered** pairings the UI actually uses (not just intended ones).
Targets: 4.5:1 normal text, 3:1 large text / UI.

| Pairing (light) | Ratio | Result |
| --- | --- | --- |
| `text` `#0e1315` on `surface` white | ~17:1 | ✅ AAA |
| `text-muted` `#536c79` on white | 5.54:1 | ✅ AA |
| `text-subtle` `#678898` on white | 3.78:1 | ✅ large/UI only (intended use) |
| white on `primary` `#345498` | 7.32:1 | ✅ AAA |
| `text-primary` `#345498` on white | 7.32:1 | ✅ AAA |
| `text-success` `#456831` on white | 6.41:1 | ✅ AAA |
| `text-info` `#375e95` on white | 6.57:1 | ✅ AAA |
| `text-warning` `#97651b` on white | 5.01:1 | ✅ AA |
| white on `danger` `#c2453d` (solid btn) | 4.99:1 | ✅ AA |
| `text-danger` `#c2453d` on white | 4.99:1 | ✅ AA |
| `text` on `bubble-out` `#d9e1f2` | ~13:1 | ✅ AAA |

| Pairing (dark) | Ratio | Result |
| --- | --- | --- |
| `text` `#f0f3f5` on `surface` `#151b1e` | ~15:1 | ✅ AAA |
| `text-muted` `#a4b7c1` on surface | 8.39:1 | ✅ AAA |
| `text-primary` `#6787cb` on surface | 4.90:1 | ✅ AA |
| `on-primary` `#0e1315` on `primary` fill `#6787cb` | 4.90:1 | ✅ AA |
| `text-primary` link `#8da5d8` on `bg` `#0e1315` | 7.06:1 | ✅ AAA |

**Rejected pairings / fixes applied:**
- `lavender-500` as primary text on white was usable (5.26:1) but **`lavender-600` chosen**
  for an AAA margin on the heavily-used button/link path.
- `lavender-400` button with **white** text in dark mode = 3.56:1 → **rejected**; resolved by
  flipping `on-primary` to dark in dark mode (4.90:1).
- `text-subtle` is restricted to non-essential text (timestamps, placeholders); never used
  for primary reading content.

---

## 6. Components & anti-duplication

One canonical implementation per primitive (see [COMPONENT_AUDIT.md](COMPONENT_AUDIT.md) and
[COMPONENT_MAP.md](COMPONENT_MAP.md)). Notable decisions:

- **New primitive `Badge`** consolidates the inline pill/chip/status-dot pattern that was
  hand-rolled in ≥4 places. Variant-driven (`tone` + optional `dot`).
- **Shared `navItems` config** feeds both `BottomNav` (portrait tabs) and `NavRail` (desktop
  rail); renderers stay distinct, data does not drift.
- All status color lives behind `success` / `warning` / `danger` / `info` / `primary` tokens.
  No raw Tailwind palette classes (`yellow-500`, `blue-100`, `gray-500`, …) remain in
  component code.
