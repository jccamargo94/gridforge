import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, RefObject } from "react";
import {
  clampWindow,
  fullWindow,
  isWindowFull,
  panRange,
  windowSpan,
  zoomRange,
  type ChartZoomWindow,
} from "@/lib/chart-zoom";

const ZOOM_STEP = 1.3;

type PanBlockedPredicate = (target: EventTarget | null) => boolean;

export function useChartZoom<T>(data: T[], minWindow = 4) {
  const total = data.length;
  const [zoomWindow, setZoomWindow] = useState<ChartZoomWindow>(() => fullWindow(total));
  const [prevTotal, setPrevTotal] = useState(total);
  const wrapperRef: RefObject<HTMLDivElement | null> = useRef(null);
  const dragRef = useRef<{ anchorX: number; anchorStart: number } | null>(null);

  if (prevTotal !== total) {
    setPrevTotal(total);
    setZoomWindow(fullWindow(total));
  }

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const ratio = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0.5;
      const factor = e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setZoomWindow((current) => zoomRange(current, ratio, factor, total, minWindow));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [total, minWindow]);

  // External controls (e.g. the recharts Brush) feed ranges through here so
  // they share the same visible window as wheel zoom and pan.
  const setWindow = useCallback(
    (next: ChartZoomWindow) => {
      setZoomWindow(clampWindow(next, total, minWindow));
    },
    [total, minWindow]
  );

  const handleMouseDown = useCallback(
    (e: MouseEvent<HTMLDivElement>, isPanBlocked?: PanBlockedPredicate) => {
      if (isPanBlocked?.(e.target)) return;
      if (total <= 1 || isWindowFull(zoomWindow, total)) return;
      dragRef.current = { anchorX: e.clientX, anchorStart: zoomWindow.start };
    },
    [total, zoomWindow]
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      const el = wrapperRef.current;
      if (!drag || !el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return;
      const span = windowSpan(zoomWindow);
      const delta = ((e.clientX - drag.anchorX) / rect.width) * span;
      setZoomWindow((current) => panRange(current, drag.anchorStart + delta - current.start, total));
    },
    [total, zoomWindow]
  );

  const endDrag = useCallback(() => {
    dragRef.current = null;
  }, []);

  const reset = useCallback(() => {
    setZoomWindow(fullWindow(total));
  }, [total]);

  const visibleData = total === 0 ? [] : data.slice(zoomWindow.start, zoomWindow.end + 1);

  return {
    wrapperRef,
    window: zoomWindow,
    visibleData,
    isZoomed: !isWindowFull(zoomWindow, total),
    reset,
    setWindow,
    getWrapperProps: (isPanBlocked?: PanBlockedPredicate) => ({
      onMouseDown: (e: MouseEvent<HTMLDivElement>) => handleMouseDown(e, isPanBlocked),
      onMouseMove: handleMouseMove,
      onMouseUp: endDrag,
      onMouseLeave: endDrag,
      onDoubleClick: reset,
    }),
  };
}
