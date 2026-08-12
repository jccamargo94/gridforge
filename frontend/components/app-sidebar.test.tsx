import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/lib/theme-context";
import { I18nProvider } from "@/lib/i18n-context";
import { AppSidebar } from "./app-sidebar";

vi.mock("next/navigation", () => ({ usePathname: () => "/runs" }));

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
});
