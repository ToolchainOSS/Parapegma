# Component Map — migration ledger

Living record of the re-theme + consolidation. Status values: **migrated** (re-themed in
place via tokens), **consolidated** (folded into a canonical primitive), **new**, **deleted**,
**kept-as-is** (intentional, reason given). Zero entries are "duplicate, not yet resolved".

## New primitives / shared modules

| Item | File | Role |
| --- | --- | --- |
| `Badge` | [web/src/components/Badge.tsx](web/src/components/Badge.tsx) | **new** — canonical read-only pill/status-dot (`<span>`). `tone` + `dot`. |
| `Chip` | [web/src/components/ui/Chip.tsx](web/src/components/ui/Chip.tsx) | **new** — canonical *selectable* pill (`<button aria-pressed>`). Split from `Badge` by interactivity, not appearance. `block` switches pill → full-width row. |
| `ChipGroup` | [web/src/components/ui/ChipGroup.tsx](web/src/components/ui/ChipGroup.tsx) | **new** — single-select (or action) group, generic in the option type. `layout` = `wrap` \| `stack`. |
| `ScaleControl` | [web/src/components/ui/ScaleControl.tsx](web/src/components/ui/ScaleControl.tsx) | **new** — the one anchored 1–N rating instrument. |
| `framingOf()` / `FramingChip` | [web/src/pages/spark/FramingChip.tsx](web/src/pages/spark/FramingChip.tsx) | **new** — total lookup from an untrusted frame string to a framing definition, plus the vibe marker pill. |
| `NAV_ITEMS` config | [web/src/config/nav.tsx](web/src/config/nav.tsx) | **new** — single source of truth for primary navigation data. |

## Claude re-theme round — Spark de-duplication

| Old (duplicated) | New canonical | Status |
| --- | --- | --- |
| `.spark-chip` in [spark.css](web/src/pages/spark/spark.css), used across 6 Spark files | `Chip` / `ChipGroup` | consolidated + deleted |
| `.spark-scale` + local `ScaleControl` in [CueStep.tsx](web/src/pages/spark/CueStep.tsx) **and** inline scale in [ReflectStep.tsx](web/src/pages/spark/ReflectStep.tsx) | `ScaleControl` | consolidated (two renderings of one research instrument) |
| `ContinueBtn` local component in [Spark.tsx](web/src/pages/Spark.tsx), 12 call sites | `Button size="lg" className="w-full mt-5"` | consolidated + deleted |
| `.spark-back-btn` | `IconButton` | consolidated + deleted |
| `.spark-home-card` / `.spark-cond-grid` | `Card` + a Tailwind grid | consolidated + deleted |
| `.spark-framechip` re-typed in SparkCard / SparkSampler / RankedList | `FramingChip` | consolidated |
| `FRAMINGS[x] ?? FRAMINGS.calm` in 4 files | `framingOf()` | consolidated |
| Eyebrow + `h2` + lede triple, re-typed in 6 Spark surfaces | `SectionHeader` (`eyebrow` + `size="lg"`) | consolidated |
| `.spark-voice-*`, `.spark-timer-*`, `.spark-fitbar*`, `.spark-progress*`, `.spark-thinking` layout | Tailwind utilities | migrated |
| `--sf-*` vibe palette (inline `style={{ color: f.colorVar }}`) | `--color-frame-*` theme tokens → `text-frame-*` / `bg-frame-*` classes | migrated |
| `.spark-zone` token-alias shim (`--text`, `--surface`, …) | deleted — no hand-written stylesheet left to alias for | deleted |
| `rounded-[var(--radius-*)]` / `shadow-[var(--shadow-*)]`, 56 occurrences across 24 files | canonical `rounded-*` / `shadow-*` utilities generated from the theme | migrated |
| Bold sans `h1`/`h2` across 10 pages | `display-lg` / `display-sm` serif utilities | migrated |

## Inline badge/pill patterns → `Badge`

| Old (inline) | New canonical | Status |
| --- | --- | --- |
| Condition pills `bg-blue-100/purple/amber/emerald` in [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx) | `Badge` tone A→primary, B→accent, C→warning, D→success | consolidated + deleted old `conditionPillClass` |
| Debug fallback pill `bg-muted text-text-subtle` (**undefined token bug**) in MessageBubble | `Badge tone="neutral"` | consolidated (latent bug removed) |
| Connection-status pill `statusColors{}` in [ChatHeader.tsx](web/src/components/ui/ChatHeader.tsx) | `Badge` online→success / reconnecting→warning / offline→neutral | consolidated + deleted old `statusColors` |
| Membership-status pill `colors{}` in [Admin.tsx](web/src/pages/Admin.tsx) | `Badge` active→success / paused→warning / ended→danger / default→neutral | consolidated + deleted old `colors` map |
| Unread dot `span.w-2.h-2.rounded-full.bg-primary` in [ListRow.tsx](web/src/components/ui/ListRow.tsx) | `Badge dot tone="primary"` | consolidated |
| Unread dot `div.w-2.h-2.rounded-full.bg-primary` in [Updates.tsx](web/src/pages/Updates.tsx) | `Badge dot tone="primary"` | consolidated |

## Navigation data → `NAV_ITEMS`

| Old | New | Status |
| --- | --- | --- |
| `navItems` array in [BottomNav.tsx](web/src/components/ui/BottomNav.tsx) | imports `NAV_ITEMS` (filters `adminOnly`) | consolidated |
| `navItems` array in [NavRail.tsx](web/src/components/shell/NavRail.tsx) | imports `NAV_ITEMS` (admin gated by role) | consolidated |

> Renderers kept separate by design: `BottomNav` = horizontal tabs (portrait), `NavRail` =
> vertical rail (desktop). Only the **data** was unified, eliminating drift.

## Hardcoded color → token (re-themed in place)

| File | Change | Status |
| --- | --- | --- |
| [Button.tsx](web/src/components/Button.tsx) | `text-white`→`text-on-primary`; danger `text-white`→`text-on-danger`; secondary hover `bg-border`→`bg-surface-3` | migrated |
| [Alert.tsx](web/src/components/Alert.tsx) | warning `yellow-500/600`→`warning` token | migrated |
| [Layout.tsx](web/src/components/Layout.tsx) | register button `text-white`→`text-on-primary` | migrated |
| [MessageBubble.tsx](web/src/components/ui/MessageBubble.tsx) | `text-red-500`→`text-danger` | migrated |
| [UpdatesPage.tsx](web/src/pages/UpdatesPage.tsx) | `text-gray-500`→`text-text-muted`; `hover:bg-black/5 dark:hover:bg-white/10`→`hover:bg-surface-2` | migrated |
| [manifest.json](web/public/manifest.json) | `theme_color #f2f3f5`→`#f0f3f5` (blue-slate-50) | migrated |
| [index.html](web/index.html) | single `theme-color`→light/dark media-aware (`#f0f3f5` / `#0e1315`) | migrated |
| [index.css](web/src/index.css) | entire `@theme` repointed to new palette + raw 5 scales + typography + `on-danger` | migrated |

## Token additions

| Token | Reason |
| --- | --- |
| `--color-on-danger` | dark-mode danger fill lightens; white text would fail (3.26:1). Flips to dark text (5.35:1). |
| `--color-accent` | granite secondary accent (Badge `accent`, condition B). |
| `--color-info` | explicit info token (powder-blue) — previously info reused `primary`. |
| `--font-sans` / `--font-display` | humanist system stack + heading tracking. |
| Raw `--color-<scale>-<step>` (5 × 11) | full palette scales behind the semantic aliases. |

## Kept-as-is (intentional, not duplication)

| Item | Reason |
| --- | --- |
| `PageHeader` / `ChatHeader` / `Layout` top nav | Three distinct header roles (page title / interactive chat bar / app nav). |
| 7 shell files (`AppShell`, `ChatAppShell`, `MobileShell`, `ChatShell`, `SideRailShell`, `ChatShellSide`, `NavRail`) | Deliberate responsive architecture (portrait vs desktop switch), not copy-paste. |
| `bg-black/40` modal scrim in [Dashboard.tsx](web/src/pages/Dashboard.tsx) | Neutral overlay scrim; intentionally untinted, not a brand color. |
| Existing `text-[15px]`/`text-[17px]` chat sizes | Tuned chat density; within the type-scale intent, not worth call-site churn. |

## Single-implementation primitives (verified — no siblings)

`Button`, `Card`/`CardHeader`/`CardContent`, `Input`, `Alert`, `Badge`, `IconButton`,
`SectionHeader`, `Composer`, `MessageBubble`, `ListRow`, `PageHeader`, `ChatHeader`,
`BottomNav`, `NavRail`. No `*V2`, `Primary*`, or second-implementation files exist.
