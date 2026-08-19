const CANVAS_WIDTH = 600;
const CANVAS_HEIGHT = 400;

interface Point { x: number; y: number; }

export interface ZoneEdge { from: string; to: string; }

export function computeZoneLayout(
  zones: string[],
  branches: ZoneEdge[],
): Record<string, Point> {
  const n = zones.length;
  if (n === 0) return {};
  const cx = CANVAS_WIDTH / 2;
  const cy = CANVAS_HEIGHT / 2;
  const radius = Math.min(CANVAS_WIDTH, CANVAS_HEIGHT) * 0.38;
  const pos: Record<string, Point> = {};
  zones.forEach((zone, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[zone] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });
  if (n === 1) return pos;

  const k = Math.sqrt((CANVAS_WIDTH * CANVAS_HEIGHT) / n) * 0.35;
  const iterations = 200;
  const known = new Set(zones);

  for (let iter = 0; iter < iterations; iter++) {
    const temp = 1 - iter / iterations;
    const disp: Record<string, Point> = {};
    zones.forEach((zone) => { disp[zone] = { x: 0, y: 0 }; });

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = zones[i];
        const b = zones[j];
        let dx = pos[a].x - pos[b].x;
        let dy = pos[a].y - pos[b].y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
        const force = (k * k) / dist;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        disp[a].x += dx;
        disp[a].y += dy;
        disp[b].x -= dx;
        disp[b].y -= dy;
      }
    }

    for (const edge of branches) {
      if (!known.has(edge.from) || !known.has(edge.to)) continue;
      let dx = pos[edge.from].x - pos[edge.to].x;
      let dy = pos[edge.from].y - pos[edge.to].y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const force = (dist * dist) / k;
      dx = (dx / dist) * force;
      dy = (dy / dist) * force;
      disp[edge.from].x -= dx;
      disp[edge.from].y -= dy;
      disp[edge.to].x += dx;
      disp[edge.to].y += dy;
    }

    zones.forEach((zone) => {
      const d = Math.sqrt(disp[zone].x * disp[zone].x + disp[zone].y * disp[zone].y);
      const step = d > 0 ? Math.min(d, temp) / d : 0;
      pos[zone].x += disp[zone].x * step;
      pos[zone].y += disp[zone].y * step;
      pos[zone].x = Math.min(CANVAS_WIDTH - 30, Math.max(30, pos[zone].x));
      pos[zone].y = Math.min(CANVAS_HEIGHT - 30, Math.max(30, pos[zone].y));
    });
  }

  return pos;
}

const BLUE: [number, number, number] = [37, 99, 235];
const AMBER: [number, number, number] = [245, 158, 11];

export function lmpColor(lmp: number, min: number, max: number): string {
  if (min === max) return "#71717a";
  const t = Math.min(1, Math.max(0, (lmp - min) / (max - min)));
  const channels = BLUE.map((v, i) => Math.round(v + (AMBER[i] - v) * t));
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}