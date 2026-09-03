# Design QA — annotated UI-v2 follow-up

## Visual truth and test state

- Source visual truth: `/home/golodn1y/.codex/attachments/f3f8988c-612d-437d-a9a8-82cd2fad4ecd/codex-clipboard-4c7a1314-829a-4aa1-8968-07f491f3c538.png`
- Source pixels: 1176 × 1697 (approximately 588 × 848.5 CSS pixels at 2× density).
- Matching implementation capture: `/tmp/cleanarr-mobile-final-light.png`
- Implementation pixels and browser viewport: 590 × 850 at 1× density.
- Additional evidence: `/tmp/cleanarr-mobile-final-dark.png`, `/tmp/cleanarr-desktop-tooltip-activity.png`, and `/tmp/cleanarr-desktop-collapsed-tooltip.png`.
- State: authenticated administrator, Russian UI, Library, movies, first 12-item page, medium cards. Light and dark themes were both checked.

## Comparison

The reference and implementation were reviewed together at the same effective mobile viewport. The implementation preserves the existing CleanArr typography, semantic surfaces, purple active state, two-column artwork grid, copy hierarchy, Lucide icon language, and responsive reflow. The intentionally changed surfaces match the annotation: the web scrollbar is absent while document scrolling remains available, the bottom navigation is inset 8 px from the viewport and safe area, content reserves space above it, and solid destructive card controls remain visible without hover.

Focused desktop comparison confirmed that the collapsed rail retains every destination by icon and accessible name, the active surface moves between destinations, and a real pointer hover exposes the localized tooltip. Activity uses a dense single stream; connected services use divided rows rather than nested cards; the service editor remains within the 850 px viewport and scrolls internally.

## Fidelity checklist

- Typography: existing Geist scale and weights retained; headings and control labels remain legible at 590 px.
- Spacing and geometry: mobile content gutters remain 16 px; bottom navigation has balanced outer spacing, rounded border, safe-area offset, and matching content clearance.
- Color and theme: semantic tokens used for surfaces, focus, status, and solid destructive actions; checked in light and dark modes.
- Imagery: existing poster assets retain their aspect ratio and crop; first-page loading is bounded and lazy.
- Copy: new user, pagination, density, Settings, tooltip, and role strings are available in English and Russian; the Russian default badge is `Основной`.
- Icons and controls: Lucide icons are retained; icon-only actions have an accessible name and tooltip (native close descriptions are retained where wrapping would interfere with Escape/focus behavior).
- Accessibility and responsiveness: keyboard focus return, selection reset, reduced initial tab motion, mobile overflow, safe-area spacing, viewer-disabled reasons, and responsive Settings access were exercised.

## Findings and fixes

1. **P1 — visible mobile web scrollbar and bottom bar flush to the viewport edge.** Fixed with mobile-only scrollbar suppression, retained scrolling, an 8 px/safe-area bottom inset, and increased content clearance. Verified in the light and dark captures.
2. **P1 — icon tooltip trigger props were initially swallowed by the animated-icon wrapper.** Fixed by rendering the actual button through the tooltip trigger. Verified with a real pointer hover; `Активность` is visible in `/tmp/cleanarr-desktop-tooltip-activity.png`.
3. **P2 — Settings subsections were not reachable after moving Settings into the mobile More sheet.** Fixed by exposing all five sections in that sheet and giving More the shared active state for Users/Settings. Verified at 590 × 850.
4. **P2 — a self-demoted administrator could retain stale administrative controls until reload.** Fixed by applying the returned current-user role to the active workspace immediately; backend authorization already resolves the persisted role per request.
5. **P1 — the long torrent-client editor was visually clipped even though its custom viewport reported scroll styling.** Replaced the flex-trapped viewport with a bounded, keyboard-focusable native scroll region using themed scrollbar tokens. At 590 × 850, an actual wheel gesture moved the form from `scrollTop=0` to `scrollTop=472` while the fixed footer remained visible.
6. **P2 — the disabled SSO Client Secret icon action had an accessible name but no hover tooltip.** Moved the tooltip trigger to a non-disabled wrapper so the localized explanation is available even while SSO is disabled; verified with a real pointer hover.
7. **P1 — the browser fixture and assertions still reflected the pre-role, pre-account-redesign shell.** Added the explicit administrator fixture role, updated theme checks for the new directly accessible desktop controls, localized the downloader profile expectation, and retargeted the setup-wizard scroll assertion to its labelled native region.

No actionable P0, P1, or P2 visual or interaction findings remain. The production build reports only the existing large-chunk advisory; it does not affect this visual acceptance pass.

final result: passed
