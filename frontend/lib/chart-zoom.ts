export interface ChartZoomWindow {
  start: number;
  end: number;
}

export function fullWindow(total: number): ChartZoomWindow {
  return { start: 0, end: Math.max(0, total - 1) };
}

export function windowSpan(window: ChartZoomWindow): number {
  return window.end - window.start + 1;
}

export function isWindowFull(window: ChartZoomWindow, total: number): boolean {
  return window.start === 0 && window.end >= total - 1;
}

export function clampIndex(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}

/**
 * Zoom a window around the point located at `focusRatio` (0..1 across the full
 * data). `factor < 1` zooms in (window shrinks), `factor > 1` zooms out.
 */
export function zoomRange(
  current: ChartZoomWindow,
  focusRatio: number,
  factor: number,
  total: number,
  minWindow: number
): ChartZoomWindow {
  if (total <= 1) return fullWindow(total);

  const span = windowSpan(current);
  const minSpan = Math.min(minWindow, total);
  const newSpan = clampIndex(span * factor, minSpan, total);

  if (newSpan === span) return current;

  const ratio = Math.max(0, Math.min(1, focusRatio));
  const focusIndex = ratio * (total - 1);
  const relative =
    span > 1 ? Math.max(0, Math.min(1, (focusIndex - current.start) / (span - 1))) : 0.5;

  const start = clampIndex(focusIndex - relative * (newSpan - 1), 0, total - newSpan);
  return { start, end: start + newSpan - 1 };
}

export function panRange(
  current: ChartZoomWindow,
  delta: number,
  total: number
): ChartZoomWindow {
  const span = windowSpan(current);
  const maxStart = Math.max(0, total - span);
  const start = clampIndex(current.start + delta, 0, maxStart);
  return { start, end: start + span - 1 };
}
