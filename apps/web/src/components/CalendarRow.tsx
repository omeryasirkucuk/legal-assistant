import { Bell, CalendarDays, Check, ChevronRight, Clock3, Gavel, Handshake, MapPin } from "lucide-react";
import { branchName } from "@/components/DeadlineForm";
import { type CalendarItem, calendarTime, kindColor, kinds } from "@/lib/calendar";
import { formatDay } from "@/lib/dates";
import { t } from "@/lib/i18n";

const icons = { deadline: Clock3, hearing: Gavel, meeting: Handshake, reminder: Bell, event: CalendarDays };

export function CalendarRow({ item, matter, showDate, onEdit }: {
  item: CalendarItem;
  matter?: string;
  showDate?: boolean;
  onEdit: () => void;
}) {
  const Icon = item.done ? Check : icons[item.kind];
  const branch = item.kind === "deadline" ? branchName(item.branch) : "";
  const details = [showDate && formatDay(item.due), calendarTime(item), branch, matter].filter(Boolean);

  return (
    <li>
      <button type="button" onClick={onEdit} className="group flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-desk sm:px-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${item.done ? "bg-desk text-faint" : kindColor[item.kind]}`}>
          <Icon size={17} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className={`break-words [overflow-wrap:anywhere] ${item.done ? "text-muted line-through" : "font-medium text-ink"}`}>{item.label}</span>
            <span className="text-xs text-muted">{t(kinds[item.kind])}</span>
          </span>
          {details.length > 0 && <span className="block text-xs text-muted">{details.join(" · ")}</span>}
          {item.kind !== "deadline" && item.location && (
            <span className="mt-0.5 flex items-center gap-1 text-xs text-muted"><MapPin size={12} className="shrink-0" /> <span className="truncate">{item.location}</span></span>
          )}
        </span>
        {item.kind !== "deadline" && item.remind_at && !item.reminder_dismissed && !item.done && (
          <span title={t("calendarAlert")}><Bell size={15} className="shrink-0 text-muted" /></span>
        )}
        <ChevronRight size={15} className="shrink-0 text-faint group-hover:text-cite" />
      </button>
    </li>
  );
}
