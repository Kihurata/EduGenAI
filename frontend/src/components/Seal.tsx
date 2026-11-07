export function Seal({ text = "ĐÃ DUYỆT" }: Readonly<{ text?: string }>) {
  return (
    <span className="inline-block -rotate-6 rounded-sm border-2 border-son px-3 py-1 text-sm font-semibold tracking-widest text-son">
      {text}
    </span>
  );
}
