# Third-party UI provenance

- **Animate UI Tabs**: local `src/components/ui/tabs.tsx` adapts the animated highlight
  from the [official Tabs reference](https://animate-ui.com/docs/components/animate/tabs)
  while retaining the project's Base UI keyboard and ARIA semantics.
  The reference is distributed by Animate UI under **MIT + Commons Clause**; no registry
  code importing the obsolete `@base-ui-components/react` package was copied.
- **React Bits FadeContent**: downloader profile rows use a local, presentation-only
  Motion reveal inspired by [React Bits FadeContent](https://github.com/DavidHDev/react-bits).
  React Bits is distributed under **MIT + Commons Clause**. No React Bits package, GSAP,
  ScrollTrigger, or Pro source is included.
