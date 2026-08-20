import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/lib/theme-context";
import { I18nProvider } from "@/lib/i18n-context";
import { AppSidebar } from "./app-sidebar";

const pathname = { current: "/runs" };
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
}));

const signOut = vi.fn();
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ signOut }) }));

function renderSidebar() {
  return render(
    <ThemeProvider>
      <I18nProvider>
        <AppSidebar />
      </I18nProvider>
    </ThemeProvider>
  );
}

describe("AppSidebar", () => {
  it("renders the three nav links pointing at the right routes", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /ejecuciones/i })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: /escenarios/i })).toHaveAttribute("href", "/scenarios");
    expect(screen.getByRole("link", { name: /comparar/i })).toHaveAttribute("href", "/compare");
  });

  it("marks the current route active", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /ejecuciones/i })).toHaveClass("text-amber-400");
    expect(screen.getByRole("link", { name: /escenarios/i })).not.toHaveClass("text-amber-400");
  });

  it("calls signOut when Salir is clicked", () => {
    renderSidebar();
    screen.getByRole("button", { name: /salir/i }).click();
    expect(signOut).toHaveBeenCalled();
  });

  it("shows a Nodal nav item linking to /nodal", () => {
    render(
      <ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>,
    );
    const link = screen.getByRole("link", { name: /nodal/i });
    expect(link).toHaveAttribute("href", "/nodal");
  });

  it("marks the Nodal item active on /nodal", () => {
    pathname.current = "/nodal";
    render(<ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>);
    expect(screen.getByRole("link", { name: /nodal/i })).toHaveClass("text-amber-400");
  });

  it("marks the Nodal item active on a nodal dashboard route", () => {
    pathname.current = "/runs/some-id/nodal";
    render(<ThemeProvider><I18nProvider><AppSidebar /></I18nProvider></ThemeProvider>);
    expect(screen.getByRole("link", { name: /nodal/i })).toHaveClass("text-amber-400");
  });
});
