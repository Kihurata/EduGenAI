/** Decorative bronze-drum (bottom-right) and three cranes (top-right). Behind content, no pointer events. */
const RINGS = [290, 262, 214, 172, 132, 96, 60];
const TICKS = Array.from({ length: 48 }, (_, i) => (i * Math.PI) / 24);
const DOTS = Array.from({ length: 36 }, (_, i) => (i * Math.PI) / 18);
const STAR = Array.from({ length: 24 }, (_, i) => {
  const a = (i * Math.PI) / 12 - Math.PI / 2;
  const r = i % 2 ? 34 : 92;
  return `${i ? "L" : "M"}${(r * Math.cos(a)).toFixed(1)} ${(r * Math.sin(a)).toFixed(1)}`;
}).join("");

function Crane({ x, y, w }: Readonly<{ x: number; y: number; w: number }>) {
  return (
    <svg x={x} y={y} width={w} height={w * 0.6} viewBox="0 0 200 120" fill="currentColor">
      <path d="M100 60 C70 30 30 25 5 35 C35 40 60 55 80 70Z" />
      <path d="M100 60 C130 30 170 25 195 35 C165 40 140 55 120 70Z" />
      <path d="M80 70 C95 78 110 78 125 68 L150 75 C130 85 100 92 80 82Z" />
      <path d="M125 68 C135 55 142 50 150 52 L162 50 L152 56 C148 62 140 72 130 75Z" />
      <path d="M82 80 L28 104 L32 106 L84 84Z" />
    </svg>
  );
}

export function MotifBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 hidden overflow-hidden text-accent md:block">
      <svg className="absolute -bottom-40 -right-40 h-[560px] w-[560px] opacity-[0.07]" viewBox="-300 -300 600 600" fill="none" stroke="currentColor">
        {RINGS.map((r, i) => (
          <circle key={r} r={r} strokeWidth={i === 0 ? 3 : 2} />
        ))}
        <path d={`${STAR}Z`} strokeWidth="2" />
        {TICKS.map((a) => (
          <line key={a} x1={216 * Math.cos(a)} y1={216 * Math.sin(a)} x2={250 * Math.cos(a)} y2={250 * Math.sin(a)} strokeWidth="2" />
        ))}
        {DOTS.map((a) => (
          <circle key={a} cx={152 * Math.cos(a)} cy={152 * Math.sin(a)} r="3" strokeWidth="1.5" />
        ))}
      </svg>
      <svg className="absolute right-8 top-14 h-28 w-72 opacity-[0.09]" viewBox="0 0 300 120">
        <Crane x={0} y={20} w={90} />
        <Crane x={110} y={0} w={64} />
        <Crane x={190} y={50} w={48} />
      </svg>
    </div>
  );
}
