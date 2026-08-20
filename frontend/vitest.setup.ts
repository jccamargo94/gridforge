import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine, so Recharts' ResponsiveContainer (which sizes
// itself via ResizeObserver) never measures a non-zero size and renders
// nothing. Stub it to synchronously report a fixed size on observe().
class ResizeObserverStub {
  private cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe(target: Element) {
    this.cb(
      [{ target, contentRect: { width: 500, height: 320 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver
    );
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

// jsdom has no DOMMatrixReadOnly; React Flow reads m22 (the zoom factor) from
// the viewport transform when re-measuring node internals after a node's
// dimensions change (e.g. pill -> card expansion in the network graph).
class DOMMatrixReadOnlyStub {
  readonly m22: number;
  constructor(transform = "") {
    const match = /scale\(([\d.]+)\)/.exec(transform);
    this.m22 = match ? Number(match[1]) : 1;
  }
}
globalThis.DOMMatrixReadOnly =
  DOMMatrixReadOnlyStub as unknown as typeof DOMMatrixReadOnly;

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query === "(prefers-color-scheme: dark)",
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
