import { describe, expect, it } from "vitest";
import { parseOffers } from "./offer-parse";

describe("parseOffers", () => {
  it("parses resource,price lines and treats a bare name as published", () => {
    expect(parseOffers("TERMO1, 320000\n\nTERMO2\n SALTO ,abc")).toEqual([
      { resource: "TERMO1", price_cop_mwh: 320000 },
      { resource: "TERMO2", price_cop_mwh: null },
      { resource: "SALTO", price_cop_mwh: null },
    ]);
  });
});
