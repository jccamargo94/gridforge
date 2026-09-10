import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChartZoom } from "./use-chart-zoom";

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function ZoomHarness({ data }: { data: number[] }) {
  const { wrapperRef, visibleData, window, isZoomed, reset, setWindow, getWrapperProps } =
    useChartZoom(data);
  return (
    <div ref={wrapperRef} {...getWrapperProps()}>
      <span data-testid="count">{visibleData.length}</span>
      <span data-testid="window">{`${window.start}-${window.end}`}</span>
      <span data-testid="zoomed">{String(isZoomed)}</span>
      <button type="button" onClick={() => setWindow({ start: 10, end: 11 })}>
        range
      </button>
      <button type="button" onClick={reset}>
        reset
      </button>
    </div>
  );
}

function GuardHarness({ data }: { data: number[] }) {
  const { wrapperRef, window, visibleData, getWrapperProps } = useChartZoom(data);
  return (
    <div
      ref={wrapperRef}
      {...getWrapperProps(
        (target) => target instanceof Element && target.closest(".recharts-brush") != null
      )}
    >
      <span data-testid="count">{visibleData.length}</span>
      <span data-testid="window">{`${window.start}-${window.end}`}</span>
      <div data-testid="brush" className="recharts-brush">
        <span>brush area</span>
      </div>
    </div>
  );
}

function mockWidth(el: HTMLElement, width = 800) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    width,
    height: 320,
    left: 0,
    right: width,
    top: 0,
    bottom: 320,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

describe("useChartZoom", () => {
  it("starts with the full data visible", () => {
    render(<ZoomHarness data={HOURS} />);
    expect(screen.getByTestId("count")).toHaveTextContent("24");
    expect(screen.getByTestId("zoomed")).toHaveTextContent("false");
  });

  it("zooms in when scrolling up (deltaY < 0)", () => {
    render(<ZoomHarness data={HOURS} />);
    fireEvent.wheel(screen.getByTestId("count").parentElement!, {
      deltaY: -100,
      clientX: 400,
    });

    const count = Number(screen.getByTestId("count").textContent);
    expect(count).toBeGreaterThanOrEqual(4);
    expect(count).toBeLessThan(24);
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");
  });

  it("zooms back out to the full window when scrolling down", () => {
    render(<ZoomHarness data={HOURS} />);
    const wrapper = screen.getByTestId("count").parentElement!;
    fireEvent.wheel(wrapper, { deltaY: -100, clientX: 400 });
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");

    fireEvent.wheel(wrapper, { deltaY: 100, clientX: 400 });
    fireEvent.wheel(wrapper, { deltaY: 100, clientX: 400 });
    fireEvent.wheel(wrapper, { deltaY: 100, clientX: 400 });
    expect(screen.getByTestId("zoomed")).toHaveTextContent("false");
  });

  it("resets the window to the full data on reset", () => {
    render(<ZoomHarness data={HOURS} />);
    fireEvent.wheel(screen.getByTestId("count").parentElement!, { deltaY: -100, clientX: 400 });
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");

    fireEvent.click(screen.getByText("reset"));
    expect(screen.getByTestId("count")).toHaveTextContent("24");
    expect(screen.getByTestId("zoomed")).toHaveTextContent("false");
  });

  it("cannot zoom in past the minimum window", () => {
    render(<ZoomHarness data={HOURS} />);
    const wrapper = screen.getByTestId("count").parentElement!;
    for (let i = 0; i < 10; i++) {
      fireEvent.wheel(wrapper, { deltaY: -100, clientX: 400 });
    }
    const count = Number(screen.getByTestId("count").textContent);
    expect(count).toBe(4);
  });

  it("pans the window when dragging after zooming in", () => {
    render(<ZoomHarness data={HOURS} />);
    const wrapper = screen.getByTestId("count").parentElement!;
    mockWidth(wrapper);
    fireEvent.wheel(wrapper, { deltaY: -100, clientX: 400 });
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");

    const before = Number(screen.getByTestId("count").textContent);
    fireEvent.mouseDown(wrapper, { clientX: 100 });
    fireEvent.mouseMove(wrapper, { clientX: 300 });
    fireEvent.mouseUp(wrapper, { clientX: 300 });

    expect(Number(screen.getByTestId("count").textContent)).toBe(before);
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");
  });

  it("exposes the window and clamps an external range to the minimum span", () => {
    render(<ZoomHarness data={HOURS} />);
    fireEvent.click(screen.getByText("range"));

    expect(screen.getByTestId("window")).toHaveTextContent("10-13");
    expect(screen.getByTestId("count")).toHaveTextContent("4");
    expect(screen.getByTestId("zoomed")).toHaveTextContent("true");
  });

  it("ignores pan presses that start inside a blocked target", () => {
    render(<GuardHarness data={HOURS} />);
    const wrapper = screen.getByTestId("count").parentElement!;
    mockWidth(wrapper);
    fireEvent.wheel(wrapper, { deltaY: -100, clientX: 400 });
    const zoomedWindow = screen.getByTestId("window").textContent;

    fireEvent.mouseDown(screen.getByText("brush area"), { clientX: 100 });
    fireEvent.mouseMove(wrapper, { clientX: 300 });

    expect(screen.getByTestId("window")).toHaveTextContent(zoomedWindow!);
  });

  it("still pans when the press starts outside the blocked target", () => {
    render(<GuardHarness data={HOURS} />);
    const wrapper = screen.getByTestId("count").parentElement!;
    mockWidth(wrapper);
    fireEvent.wheel(wrapper, { deltaY: -100, clientX: 400 });
    const before = screen.getByTestId("window").textContent;

    fireEvent.mouseDown(wrapper, { clientX: 100 });
    fireEvent.mouseMove(wrapper, { clientX: 300 });

    expect(screen.getByTestId("window")).not.toHaveTextContent(before!);
  });
});
