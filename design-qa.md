# Design QA — annotated UI-v2 follow-up

## Visual truth and test state

- Source visual truth: `/home/golodn1y/.codex/attachments/f3f8988c-612d-437d-a9a8-82cd2fad4ecd/codex-clipboard-4c7a1314-829a-4aa1-8968-07f491f3c538.png`
- Second annotation source: `/home/golodn1y/.codex/attachments/0a3782a0-017f-417c-9382-8f232b8b15d7/codex-clipboard-e41ab5d2-321a-4532-a9ac-48026d3bc307.png`
- Collapsed-tooltip source: `/tmp/codex-clipboard-25fc5ae3-c704-4fa5-9b8a-1def3d936bf3.png`
- Source pixels: 1176 × 1697 (approximately 588 × 848.5 CSS pixels at 2× density).
- Matching mobile implementation capture: `/tmp/cleanarr-ui-final-artifacts.iq4twC/data/0330970f436c21397e1764d7a34ca507151abd7b.png`
- Implementation pixels and browser viewport: 375 × 812 at 1× density; desktop evidence is 1280 × 720 at 1× density.
- Additional evidence: `/tmp/cleanarr-users-mobile-light-final.png`, `/tmp/cleanarr-users-mobile-dark-final.png`, and `/tmp/cleanarr-tooltip-final.png` at the in-app browser's 614 × 698 CSS-pixel viewport.
- Follow-up browser evidence: the `playwright-report` artifact from quality-gate run `33792774644`, with 1280 × 720 attachments `desktop-settings-tree-followup`, `desktop-collapsed-focus-followup`, `desktop-account-popover-followup`, `desktop-account-popover-dark-followup`, and `desktop-users-followup`, plus the 375 × 812 `mobile-bottom-navigation-followup` capture (downloaded locally to `/tmp/cleanarr-ui-final-artifacts.iq4twC`).
- State: authenticated administrator; Russian in the live in-app browser and English in the deterministic CI fixtures. Library, Users, Settings, compact navigation, account popover, light/dark themes, and reduced motion were checked.

## Comparison

The reference and implementation were reviewed together in a combined visual pass, including the full annotated Settings/sidebar source beside the 1280 × 720 expanded and collapsed implementations, and the tooltip-conflict crop beside the live 614 × 698 tooltip capture. The implementation preserves the existing CleanArr typography, semantic surfaces, purple active state, copy hierarchy, Lucide icon language, and responsive reflow. The intentionally changed surfaces match the annotations: sidebar scrollbars are absent while keyboard/wheel scrolling remains available, the bottom navigation is inset 8 px from the viewport and safe area, and content reserves space above it.

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
13. **P2 — the brand and account footer remained visually fragmented.** The lightning mark is separated vertically in the collapsed header and the official Animate UI GitHub Stars pattern is restored beside the brand. The edge toggle is now a compact circular control with a morphing left/right chevron, keeping its direction readable without adding another boxed sidebar row.
14. **P1 — mobile navigation and the Settings tree changed state without spatial continuity.** Both now use the shared measured Highlight primitive: the mobile active surface springs between destinations, while the Settings branch expands/collapses through AnimatePresence and its subsection surface moves between rows. Initial render and reduced-motion behavior remain non-distracting.
15. **P1 — the compact desktop selection surface was not reliably square or centered.** The rail surface is fixed at 44 × 44 px, follows bounds throughout the sidebar resize, and applies the Settings-group offset through a semantic active class. Browser coverage waits for the spring to settle and requires the surface and active icon centers to differ by less than 1 px; this exposed and fixed a persistent 7 px Settings offset.
16. **P2 — account controls consumed the bottom of the sidebar.** Only the avatar remains pinned in the footer. Identity, theme, language, and logout are grouped in an accessible popover, verified in light and dark modes with Escape dismissal and focus return to the avatar trigger.
17. **P1 — the active compact navigation surface could be covered by an inactive grey hover surface and the growing icon could clip against the navigation viewport.** Collapsed navigation now uses an exact 44 × 44 measured surface, visible overflow, centered icons, no nested icon hover box, and a transparent active-button hover state. Browser assertions verify square geometry, sub-pixel center alignment, visible inactive hover, and no active grey overlay.
18. **P2 — the collapsed rail mixed ambiguous status/storage controls with navigation.** Runtime status now uses the same compact rounded-square geometry as the rail; the storage summary is removed from collapsed mode, while the full status remains available in expanded mode and mobile More.
19. **P2 — brand, toggle, and account geometry used unrelated shapes and spacing.** The sidebar toggle returns to the familiar Menu icon inside the brand row, the lightning and toggle use balanced insets, and a separator closes the brand row in both widths. The expanded account trigger is a full-width navigation-like row with avatar and username; the collapsed trigger is the matching square avatar target.
20. **P2 — user identity and administrator guidance were fragmented across the table.** The count is in the card's top-right badge, the current-account and minimum-admin copy share one header notice, and table/footer identity use the same deterministic two-initial avatar with a stable semantic-token color.
21. **P2 — compact Settings rows only painted grey hover behind their short label.** Every subsection now occupies the measured branch width, so hover and active surfaces share one full-width rectangle while the moving purple focus remains independent.
22. **P2 — legacy compact tooltips were visually cramped and could appear to collide with the active surface.** Icon-only compact controls now use the local Animate UI/Base UI tooltip implementation with a spring entrance, semantic primary surface, full localized text, portal positioning, and reduced-motion support. The 614 × 698 pointer-hover capture and the 1280 × 720 browser test both confirm unclipped content.

The final follow-up run passed lint, 121 Vitest tests, production build, and all 15 Chromium scenarios. Its screenshots were reviewed together with the annotated source captures; the compact focus is square and centered, the active surface is not overpainted on hover, Settings rows use their full branch width, the mobile bar keeps balanced bottom spacing, and both account-popover themes are visually stable.

No actionable P0, P1, or P2 visual or interaction findings remain. The production build reports only the existing large-chunk advisory; it does not affect this visual acceptance pass.

final result: passed
