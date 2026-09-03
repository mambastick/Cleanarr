# Third-party UI provenance

- **Animate UI Tabs**: local `src/components/ui/tabs.tsx` adapts the animated highlight
  from the [official Tabs reference](https://animate-ui.com/docs/components/animate/tabs)
  while retaining the project's Base UI keyboard and ARIA semantics.
  The reference is distributed by Animate UI under **MIT + Commons Clause**; no registry
  code importing the obsolete `@base-ui-components/react` package was copied.
- **Animate UI Icons**: local `src/components/animate-ui/animated-icon.tsx` adapts the
  interaction-triggered motion pattern for repository-owned Lucide icons. The reference is
  distributed by Animate UI under **MIT + Commons Clause**; no registry package is linked at runtime.
- **Morphicons**: `morphicons` is used for stateful direction and theme icon transitions and is
  distributed under the **MIT License**. See https://github.com/guillermolg00/morphicons.
- **React Bits FadeContent**: downloader profile rows use a local, presentation-only
  Motion reveal inspired by [React Bits FadeContent](https://github.com/DavidHDev/react-bits).
  React Bits is distributed under **MIT + Commons Clause**. No React Bits package, GSAP,
  ScrollTrigger, or Pro source is included.
