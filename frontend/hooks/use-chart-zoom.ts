import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, RefObject } from "react";
import {
  fullWindow,
  isWindowFull,
  panRange,
  windowSpan,
  zoomRange,
  type ChartZoomWindow,
} from "@/lib/chart-zoom";

const ZOOM_STEP = 1.3;

export function useChartZoom<T>(data: T[], minWindow = 4) {
  const total = data.length;
  const [window, setWindow] = useState<ChartZoomWindow>(() => fullWindow(total));
  const [prevTotal, setPrevTotal] = useState(total);
  const wrapperRef: RefObject<HTMLDivElement | null> = useRef(null);
  const dragRef = useRef<{ anchorX: number; anchorStart: number } | null>(null);

  if (prevTotal !== total) {
    setPrevTotal(total);
    setWindow(fullWindow(total));
  }

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const ratio = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0.5;
      const factor = e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setWindow((current) => zoomRange(current, ratio, factor, total, minWindow));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [total, minWindow]);

  const handleMouseDown = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (total <= 1 || isWindowFull(window, total)) return;
    dragRef.current = { anchorX: e.clientX, anchorStart: window.start };
  }, [total, window]);

  const handleMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const el = wrapperRef.current;
    if (!drag || !el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const span = windowSpan(window);
    const delta = ((e.clientX - drag.anchorX) / rect.width) * span;
    setWindow((current) => panRange(current, drag.anchorStart + delta - current.start, total));
  }, [total, window]);

  const endDrag = useCallback(() => {
    dragRef.current = null;
  }, []);

  const reset = useCallback(() => {
    setWindow(fullWindow(total));
  }, [total]);

  const visibleData = total === 0 ? [] : data.slice(window.start, window.end + 1);

  return {
    wrapperRef,
    visibleData,
    isZoomed: !isWindowFull(window, total),
    reset,
    getWrapperProps: () => ({
      onMouseDown: handleMouseDown,
      onMouseMove: handleMouseMove,
      onMouseUp: endDrag,
      onMouseLeave: endDrag,
      onDoubleClick: reset,
    }),
  };
}
