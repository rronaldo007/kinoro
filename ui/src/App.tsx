import { useEffect, useState } from "react";
import EditorShell from "./features/editor-shell/EditorShell";
import type { IncomingOpen } from "./features/import-vp/HandoffPanel";

function parseKinoroUrl(raw: string): IncomingOpen | null {
  try {
    const u = new URL(raw);
    if (u.protocol !== "kinoro:") return null;
    const baseUrl = decodeURIComponent(u.searchParams.get("base_url") ?? "");
    const projectId = u.searchParams.get("project_id") ?? "";
    if (!baseUrl || !projectId) return null;
    const access = u.searchParams.get("access") ?? undefined;
    const refresh = u.searchParams.get("refresh") ?? undefined;
    return { baseUrl, projectId, rawUrl: raw, access, refresh };
  } catch {
    return null;
  }
}

export default function App() {
  const [incoming, setIncoming] = useState<IncomingOpen | null>(null);

  useEffect(() => {
    const kinoro = window.kinoro;
    if (!kinoro) return;

    kinoro.getPendingOpenUrl?.().then((url) => {
      if (url) {
        const parsed = parseKinoroUrl(url);
        if (parsed) setIncoming(parsed);
      }
    });

    const unsub = kinoro.onOpenUrl?.((url) => {
      const parsed = parseKinoroUrl(url);
      if (parsed) setIncoming(parsed);
    });
    return () => unsub?.();
  }, []);

  return <EditorShell incoming={incoming} />;
}
