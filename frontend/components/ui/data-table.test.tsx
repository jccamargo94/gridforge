import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n-context";
import { DataTable } from "./data-table";

interface Row { name: string; value: number; }

const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "value", header: "Value" },
];

const rows: Row[] = Array.from({ length: 30 }, (_, i) => ({ name: `item-${i}`, value: i }));

describe("DataTable", () => {
  it("paginates data, defaulting to the initial page size", () => {
    render(
      <I18nProvider>
        <DataTable columns={columns} data={rows} initialPageSize={10} />
      </I18nProvider>,
    );
    expect(screen.getByText("item-0")).toBeInTheDocument();
    expect(screen.getByText("item-9")).toBeInTheDocument();
    expect(screen.queryByText("item-10")).not.toBeInTheDocument();
  });

  it("changes page size via the rows-per-page select", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <DataTable columns={columns} data={rows} initialPageSize={10} pageSizeOptions={[10, 25]} />
      </I18nProvider>,
    );
    await user.selectOptions(screen.getByLabelText(/filas por pagina/i), "25");
    expect(screen.getByText("item-24")).toBeInTheDocument();
    expect(screen.queryByText("item-25")).not.toBeInTheDocument();
  });

  it("navigates to the next page", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <DataTable columns={columns} data={rows} initialPageSize={10} />
      </I18nProvider>,
    );
    await user.click(screen.getByRole("button", { name: /siguiente/i }));
    expect(screen.getByText("item-10")).toBeInTheDocument();
    expect(screen.queryByText("item-0")).not.toBeInTheDocument();
  });

  it("sorts numerically by column header click, toggling direction", async () => {
    const user = userEvent.setup();
    const unsorted: Row[] = [{ name: "b", value: 2 }, { name: "a", value: 1 }, { name: "c", value: 30 }];
    render(
      <I18nProvider>
        <DataTable columns={columns} data={unsorted} initialPageSize={10} />
      </I18nProvider>,
    );
    const header = screen.getByRole("button", { name: /^value/i });
    await user.click(header);
    const firstClick = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(firstClick).toEqual(["c", "30", "b", "2", "a", "1"]);

    await user.click(header);
    const secondClick = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(secondClick).toEqual(["a", "1", "b", "2", "c", "30"]);
  });
});
