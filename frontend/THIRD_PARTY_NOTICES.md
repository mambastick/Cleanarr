# Third-party UI provenance

- **Animate UI Tabs**: local `src/components/ui/tabs.tsx` adapts the animated highlight
  from the [official Tabs reference](https://animate-ui.com/docs/components/animate/tabs)
  while retaining the project's Base UI keyboard and ARIA semantics.
  The reference is distributed by Animate UI under **MIT + Commons Clause**; no registry
  code importing the obsolete `@base-ui-components/react` package was copied.
- **Animate UI Icons**: local `src/components/animate-ui/animated-icon.tsx` adapts the
  interaction-triggered motion pattern for repository-owned Lucide icons. The reference is
  distributed by Animate UI under **MIT + Commons Clause**; no registry package is linked at runtime.
- **Animate UI GitHub Stars and Highlight**: local
  `src/components/animate-ui/components/buttons/github-stars.tsx` and
  `src/components/animate-ui/primitives/effects/highlight.tsx` adapt the official
  [GitHub Stars](https://animate-ui.com/docs/components/buttons/github-stars) and
  [Files highlight](https://animate-ui.com/docs/components/base/files) registry sources to
  CleanArr tokens, reduced-motion behavior, semantic links, and navigation ARIA. They are
  distributed under the **MIT + Commons Clause** notice reproduced below.
- **Morphicons**: `morphicons` is used for stateful direction and theme icon transitions and is
  distributed under the **MIT License**. See https://github.com/guillermolg00/morphicons.
- **React Bits FadeContent**: downloader profile rows use a local, presentation-only
  Motion reveal inspired by [React Bits FadeContent](https://github.com/DavidHDev/react-bits).
  React Bits is distributed under **MIT + Commons Clause**. No React Bits package, GSAP,
  ScrollTrigger, or Pro source is included.

## Animate UI license notice

MIT + Commons Clause License Condition

Copyright (c) 2025 Elliot Sutton

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, and distribute the Software as part of an
application, website, or product, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

### Commons Clause restriction

You may use this Software, including for any commercial purpose, so long as you
do not sell or redistribute the components themselves in their original
form—whether alone or in a bundle.

### No warranty

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
