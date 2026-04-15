import { ChevronDown, ChevronUp, Wrench } from "lucide-react";
import HandoffPanel, {
  type IncomingOpen,
} from "../import-vp/HandoffPanel";
import SidecarStatus from "./SidecarStatus";

interface Props {
  open: boolean;
  onToggle: () => void;
  incoming: IncomingOpen | null;
}

export default function DevDrawer({ open, onToggle, incoming }: Props) {
  return (
    <footer
      className="border-t shrink-0 flex flex-col"
      style={{ backgroundColor: "#0f1013", borderColor: "#24262c" }}
    >
      <button
        type="button"
        onClick={onToggle}
        className="h-10 flex items-center gap-2 px-3 hover:bg-white/5"
      >
        <Wrench size={12} className="text-neutral-500" />
        <span className="text-xs uppercase tracking-wider text-neutral-500">
          Dev drawer
        </span>
        {incoming && !open && (
          <span className="text-[10px] text-neutral-400">
            · handoff available
          </span>
        )}
        <div className="flex-1" />
        {open ? (
          <ChevronDown size={14} className="text-neutral-500" />
        ) : (
          <ChevronUp size={14} className="text-neutral-500" />
        )}
      </button>
      {open && (
        <div
          className="border-t p-3 flex gap-3 overflow-x-auto"
          style={{ borderColor: "#24262c" }}
        >
          {incoming && <HandoffPanel incoming={incoming} />}
          <SidecarStatus />
        </div>
      )}
    </footer>
  );
}
