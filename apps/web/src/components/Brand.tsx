import Image from "next/image";
import mark from "@/app/icon.png";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-2.5">
      <Image src={mark} alt={compact ? "Folonto Legal" : ""} width={32} height={32} unoptimized />
      {!compact && <span className="whitespace-nowrap text-sm font-semibold text-ink">Folonto Legal</span>}
    </div>
  );
}
