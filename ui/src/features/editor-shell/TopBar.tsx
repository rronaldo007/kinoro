import { Film } from "lucide-react";
import type { SaveStatus } from "./useAutosave";

export type EditorPage = "edit" | "color" | "deliver";

interface Props {
  activePage: EditorPage;
  onChangePage: (page: EditorPage) => void;
  projectTitle?: string | null;
  saveState?: { status: SaveStatus; error: string | null };
}

const SAVE_LABELS: Record<SaveStatus, string> = {
  idle: "",
  saving: "Saving…",
  saved: "Saved",
  error: "Unsaved",
};

const TABS: { id: EditorPage; label: string; disabled: boolean; note?: string }[] = [
  { id: "edit", label: "Edit", disabled: false },
  { id: "color", label: "Color", disabled: true, note: "M7" },
  { id: "deliver", label: "Deliver", disabled: false },
];

export default function TopBar({ activePage, onChangePage, projectTitle, saveState }: Props) {
  const saveLabel = saveState ? SAVE_LABELS[saveState.status] : "";
  const saveColor =
    saveState?.status === "error"
      ? "#ef4444"
      : saveState?.status === "saving"
        ? "#a3a3a3"
        : "#2ecda7";
  return (
    <header
      className="h-12 flex items-center gap-4 px-4 border-b shrink-0"
      style={{ backgroundColor: "#0b0c0e", borderColor: "#24262c" }}
    >
      <div className="flex items-center gap-2">
        <div
          className="w-6 h-6 rounded-[5px] flex items-center justify-center"
          style={{ backgroundColor: "var(--color-accent)" }}
        >
          <Film size={14} color="#0b0c0e" strokeWidth={2.5} />
        </div>
        <span
          className="text-sm font-semibold tracking-tight"
          style={{ color: "var(--color-text-heading, #e5e5e5)" }}
        >
          Kinoro
        </span>
      </div>

      <nav className="flex items-center gap-1">
        {TABS.map((tab) => {
          const active = tab.id === activePage;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => !tab.disabled && onChangePage(tab.id)}
              disabled={tab.disabled}
              title={tab.disabled ? `${tab.label} — coming in ${tab.note}` : tab.label}
              className="px-3 py-1.5 text-xs font-medium rounded-[5px] disabled:cursor-not-allowed"
              style={{
                color: active
                  ? "var(--color-accent)"
                  : tab.disabled
                    ? "#3d4048"
                    : "#a3a3a3",
                backgroundColor: active ? "rgba(46, 205, 167, 0.08)" : "transparent",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      {projectTitle && (
        <div className="text-xs text-neutral-400 truncate max-w-[40ch]">
          <span className="text-neutral-600 uppercase tracking-wider text-[10px] mr-2">
            Project
          </span>
          {projectTitle}
        </div>
      )}

      {saveLabel && (
        <span
          className="text-[10px] uppercase tracking-wider tabular-nums ml-3"
          style={{ color: saveColor }}
          title={saveState?.error ?? undefined}
        >
          {saveLabel}
        </span>
      )}
    </header>
  );
}
