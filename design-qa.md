# CleanArr UI v2 design QA

## Visual comparison

- Approved source: `docs/design/ui-v2/reference-library.png`.
- Implemented desktop state: `docs/design/ui-v2/implementation-library-light-desktop.png`.
- Same-frame comparison: `docs/design/ui-v2/comparison-library-light-desktop.png`.
- CSS viewport: 1487 × 1058 at DPR 1. The in-app browser capture omits its 15 px scrollbar gutter and 11 px browser chrome inset, so the implementation was normalized to the declared CSS viewport only for the side-by-side comparison.
- Reviewed composition: 240 px navigation, five-column poster grid, hover/focus trash action, storage/runtime/account blocks, and 360 px right inspector.

## Responsive and theme evidence

- Light desktop: `docs/design/ui-v2/implementation-library-light-desktop.png`.
- Dark desktop: `docs/design/ui-v2/implementation-library-dark-desktop.png`.
- Light mobile at 375 CSS px: `docs/design/ui-v2/implementation-library-light-mobile.png`.
- Dark mobile at 375 CSS px: `docs/design/ui-v2/implementation-library-dark-mobile.png`.

## Interaction and accessibility review

- Keyboard navigation, focus return, reduced motion, destructive preflight, duplicate-submit prevention, responsive reflow, EN/RU copy, and Axe checks are covered by Vitest and Chromium Playwright gates.
- Poster images retain a fixed 2:3 box and use authenticated Blob URLs with a local fallback.
- Mobile batch actions clear the fixed bottom navigation and safe-area inset.
- Missing, stale, ambiguous, or conflicting evidence remains visibly unknown or blocked.
- Final comparison found no open P0, P1, or P2 visual discrepancies.

final result: passed
