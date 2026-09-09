import { getChartSeries } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

export function useChartSeries(days: number) {
  return useQuery({
    queryKey: ["chart-series", days],
    queryFn: () => getChartSeries(days),
  });
}
