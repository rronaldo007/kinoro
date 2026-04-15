import { useEffect, useState } from "react";
import MediaPool from "../media-pool/MediaPool";
import type { IncomingOpen } from "../import-vp/HandoffPanel";
import TopBar, { type EditorPage } from "./TopBar";
import Viewer from "./Viewer";
import Inspector from "./Inspector";
import Timeline from "./Timeline";
import DevDrawer from "./DevDrawer";
import DeliverPanel from "./DeliverPanel";
import { useProjectLoader } from "./useProjectLoader";
import { useAutosave } from "./useAutosave";
import { useTimelineShortcuts } from "./useTimelineShortcuts";

interface Props {
  incoming: IncomingOpen | null;
  projectTitle?: string | null;
}

export default function EditorShell({ incoming, projectTitle }: Props) {
  useTimelineShortcuts();
  const [activePage, setActivePage] = useState<EditorPage>("edit");
  const loader = useProjectLoader({ incoming, projectTitle });
  const save = useAutosave({
    projectId: loader.projectId,
    enabled: !loader.loading,
  });
  // Auto-open the dev drawer the first time a handoff is present so the user
  // finds the handoff panel without hunting for it. The useEffect handles
  // the case where `incoming` arrives AFTER mount via onOpenUrl — the
  // handoff's access token triggers auto-adopt + auto-import only while
  // HandoffPanel is mounted, so the drawer MUST be open then.
  const [devOpen, setDevOpen] = useState<boolean>(!!incoming);
  useEffect(() => {
    if (incoming) setDevOpen(true);
  }, [incoming]);

  return (
    <div
      className="h-screen flex flex-col text-neutral-100 font-sans overflow-hidden"
      style={{ backgroundColor: "#0b0c0e" }}
    >
      <TopBar
        activePage={activePage}
        onChangePage={setActivePage}
        projectTitle={projectTitle}
        saveState={{ status: save.status, error: save.error }}
      />

      {/* Main: 3 columns (media pool · viewer|deliver · inspector) */}
      <div className="flex-1 flex min-h-0">
        <aside
          className="w-[260px] border-r flex flex-col shrink-0"
          style={{ backgroundColor: "#0f1013", borderColor: "#24262c" }}
        >
          <MediaPool variant="list" />
        </aside>

        {activePage === "deliver" ? <DeliverPanel /> : <Viewer />}

        <Inspector />
      </div>

      {activePage === "edit" && <Timeline />}

      <DevDrawer
        open={devOpen}
        onToggle={() => setDevOpen((v) => !v)}
        incoming={incoming}
      />
    </div>
  );
}
