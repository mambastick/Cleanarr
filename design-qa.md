# Design QA — annotated UI-v2 follow-up

## Visual truth and test state

- Source visual truth: `/home/golodn1y/.codex/attachments/f3f8988c-612d-437d-a9a8-82cd2fad4ecd/codex-clipboard-4c7a1314-829a-4aa1-8968-07f491f3c538.png`
- Second annotation source: `/home/golodn1y/.codex/attachments/0a3782a0-017f-417c-9382-8f232b8b15d7/codex-clipboard-e41ab5d2-321a-4532-a9ac-48026d3bc307.png`
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
8. **P1 — expanding the five-section Settings tree at a 720 px desktop height pushed the account actions outside the viewport.** The sidebar navigation is now its own keyboard-focusable scroll region while runtime, storage, theme, language, and logout controls remain pinned and reachable.
9. **P1 — the expanded Settings tree exposed a browser scrollbar inside the sidebar.** The navigation keeps its independent wheel and keyboard scrolling, while both Firefox and WebKit scrollbar rendering are suppressed. Browser coverage asserts real overflow together with `scrollbar-width: none` and the hidden WebKit pseudo-element.
10. **P1 — destructive card actions competed with artwork in the top-right corner.** The solid destructive control now appears at the poster center on pointer hover or keyboard focus; it stays visible on touch-only devices and retains its accessible name and tooltip.
11. **P2 — the shared-layout sidebar selection could stretch in from an unrelated origin.** Desktop navigation now uses the measured Animate UI Highlight primitive and the same `350/35` spring as the Files reference, so the surface follows the destination bounds directly and does not animate in on first render.
12. **P2 — the collapsed rail reduced runtime and storage to ambiguous marks.** Dry-run/live and storage now keep recognizable Lucide icons, focusable semantic labels, and full status tooltips. Navigation icons receive a compact square hover/focus surface, matching the rest of the icon-button language.
13. **P2 — the brand and account footer remained visually fragmented.** The sidebar toggle now morphs between Lucide panel states through Morphicons, the lightning mark is separated vertically in the collapsed header, the official Animate UI GitHub Stars pattern is restored beside the brand, and account identity/actions share one compact row instead of two boxed blocks.

No actionable P0, P1, or P2 visual or interaction findings remain. The production build reports only the existing large-chunk advisory; it does not affect this visual acceptance pass.

final result: passed
