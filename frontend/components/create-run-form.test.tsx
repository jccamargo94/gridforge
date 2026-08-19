import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { CreateRunForm } from "./create-run-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

vi.mock("@/lib/api-client", () => ({
  createRun: vi.fn().mockResolvedValue({ run_id: "r1", status: "pending" }),
  listScenarios: vi.fn().mockResolvedValue([]),
}));

import { createRun } from "@/lib/api-client";

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>
  );
}

describe("CreateRunForm", () => {
  it("calls createRun with the form values on submit", async () => {
    const onCreated = vi.fn();
    renderWithQueryClient(<CreateRunForm onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: "2024-04-18" } });
    fireEvent.click(screen.getByRole("button", { name: /crear ejecucion/i }));

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({ dispatch_date: "2024-04-18", level: "preideal" })
      )
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it("submits with the default solver (cbc)", async () => {
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: "2024-04-18" } });
    fireEvent.click(screen.getByRole("button", { name: /crear ejecucion/i }));

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith(expect.objectContaining({ solver: "cbc" }))
    );
  });

  it("renders the HiGHS solver option as disabled", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    const solverTrigger = screen.getByRole("combobox", { name: /solver/i });
    await user.click(solverTrigger);

    const highsItem = screen.getByRole("option", { name: /highs/i });
    expect(highsItem).toHaveAttribute("aria-disabled", "true");
  });

  it("offers the lmp level option", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    const levelTrigger = screen.getByRole("combobox", { name: /nivel/i });
    await user.click(levelTrigger);

    expect(await screen.findByRole("option", { name: "lmp" })).toBeInTheDocument();
  });

  it("shows the nodal network editor when lmp is selected", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    const levelTrigger = screen.getByRole("combobox", { name: /nivel/i });
    await user.click(levelTrigger);
    await user.click(await screen.findByRole("option", { name: "lmp" }));

    expect(screen.getByRole("textbox", { name: /red nodal/i })).toBeInTheDocument();
  });

  it("includes nodal_network in the payload for an lmp run with a valid network", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: "2024-04-18" } });
    const levelTrigger = screen.getByRole("combobox", { name: /nivel/i });
    await user.click(levelTrigger);
    await user.click(await screen.findByRole("option", { name: "lmp" }));
    await user.click(screen.getByRole("button", { name: /cargar red de ejemplo/i }));
    await user.click(screen.getByRole("button", { name: /crear ejecucion/i }));

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          level: "lmp",
          nodal_network: expect.objectContaining({
            name: "three_zone",
            reference_zone: "norte",
          }),
        })
      )
    );
  });

  it("sends nodal_network null when the level is preideal", async () => {
    renderWithQueryClient(<CreateRunForm onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/fecha/i), { target: { value: "2024-04-18" } });
    fireEvent.click(screen.getByRole("button", { name: /crear ejecucion/i }));

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith(expect.objectContaining({ nodal_network: null }))
    );
  });
});
