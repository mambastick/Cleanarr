/// <reference types="vitest/jsdom" />
import "@testing-library/jest-dom/vitest"

// Node 25+ ships an experimental global Web Storage whose `localStorage` getter
// returns undefined unless `--localstorage-file` is set. Vitest keeps that
// existing global, so it shadows jsdom's Storage. Rebind both storages to the
// jsdom window so tests behave the same on every Node version.
for (const name of ["localStorage", "sessionStorage"] as const) {
  const storage = jsdom.window[name]
  if (globalThis[name] !== storage) {
    Object.defineProperty(globalThis, name, { configurable: true, enumerable: true, value: storage })
  }
}

Object.defineProperty(window, "scrollTo", { value: () => {}, writable: true })
