const MIN_WIDTH = 600;
const MIN_HEIGHT = 400;
const PADDING = 40;
const GAP = 16;

interface Point { x: number; y: number; }

export interface ZoneLayout {
  positions: Record<string, Point>;
  width: number;
  height: number;
  nodeRadius: number;
}

// A ring layout: nodes evenly spaced around a circle whose radius grows with
// the zone count, so adjacent node circles never overlap regardless of n.
// (The previous force-directed simulation, which also took branches as
// input, was only ever exercised against the 3-zone example network; a real
// ~18-zone mesh collapsed it into an unreadable cluster -- see the "mapa
// zonal roto" finding. Branch topology doesn't factor into node placement
// here, so it's not a parameter.)
export function computeZoneLayout(zones: string[]): ZoneLayout {
  const n = zones.length;
  if (n === 0) {
    return { positions: {}, width: MIN_WIDTH, height: MIN_HEIGHT, nodeRadius: 30 };
  }

  const nodeRadius = Math.max(14, Math.min(30, Math.round(240 / n)));
  const minSeparation = 2 * nodeRadius + GAP;
  const circleRadius = n > 1 ? minSeparation / (2 * Math.sin(Math.PI / n)) : 0;
  const side = 2 * (circleRadius + nodeRadius) + PADDING;
  const width = Math.max(MIN_WIDTH, side);
  const height = Math.max(MIN_HEIGHT, side);
  const cx = width / 2;
  const cy = height / 2;

  const positions: Record<string, Point> = {};
  zones.forEach((zone, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    positions[zone] = { x: cx + circleRadius * Math.cos(angle), y: cy + circleRadius * Math.sin(angle) };
  });

  return { positions, width, height, nodeRadius };
}

const BLUE: [number, number, number] = [37, 99, 235];
const AMBER: [number, number, number] = [245, 158, 11];

export function lmpColor(lmp: number, min: number, max: number): string {
  if (min === max) return "#71717a";
  const t = Math.min(1, Math.max(0, (lmp - min) / (max - min)));
  const channels = BLUE.map((v, i) => Math.round(v + (AMBER[i] - v) * t));
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}
