import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { LogViewer } from "./log-viewer";

vi.mock("@/lib/api-client", () => ({
  getRunLog: vi.fn(),
}));

import { getRunLog } from "@/lib/api-client";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>
  );
}

describe("LogViewer", () => {
  it("shows the log text in a <pre> when available", async () => {
    vi.mocked(getRunLog).mockResolvedValue("worker output line");

    renderWithClient(<LogViewer runId="run-1" />);

    expect(await screen.findByText("worker output line")).toBeInTheDocument();
  });

  it("shows 'no logs yet' instead of an error when there is no log yet", async () => {
    vi.mocked(getRunLog).mockResolvedValue(null);

    renderWithClient(<LogViewer runId="run-1" />);

    expect(await screen.findByText(/sin logs todavia/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
