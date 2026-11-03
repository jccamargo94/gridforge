import type { OfferToAudit } from "@/lib/types";

export function parseOffers(text: string): OfferToAudit[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [resource, price] = line.split(",").map((p) => p.trim());
      const n = price ? Number(price.replace(/\s/g, "")) : NaN;
      return { resource, price_cop_mwh: Number.isFinite(n) ? n : null };
    });
}
