import { useEffect, useState } from "react";
import {
  selectClipDuration,
  useTimelineStore,
  type Clip,
  type ClipTransition,
  type TransitionKind,
} from "../../stores/timelineStore";

export default function Inspector() {
  const selection = useTimelineStore((s) => s.selection);
  const clip = useTimelineStore((s) =>
    s.selection ? s.clips.find((c) => c.id === s.selection) ?? null : null,
  );
  const setClipSpeed = useTimelineStore((s) => s.setClipSpeed);
  const updateTextClip = useTimelineStore((s) => s.updateTextClip);
  const setClipTransition = useTimelineStore((s) => s.setClipTransition);

  const isText = clip?.type === "text";

  return (
    <aside
      className="w-[280px] border-l flex flex-col shrink-0"
      style={{ backgroundColor: "#0f1013", borderColor: "#24262c" }}
    >
      <div
        className="h-10 flex items-center px-3 border-b"
        style={{ borderColor: "#24262c" }}
      >
        <span className="text-xs uppercase tracking-wider text-neutral-500">
          Inspector
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {clip ? (
          <Section label={isText ? "Text clip" : "Clip"}>
            <Row label="start" value={`${clip.start_seconds.toFixed(3)}s`} />
            {!isText && (
              <Row label="in" value={`${clip.in_seconds.toFixed(3)}s`} />
            )}
            {!isText && (
              <Row label="out" value={`${clip.out_seconds.toFixed(3)}s`} />
            )}
            <Row
              label="duration"
              value={`${selectClipDuration(clip).toFixed(3)}s`}
            />
          </Section>
        ) : (
          <Placeholder label="Clip" note="select a clip" />
        )}

        {isText && selection && clip && (
          <TextControls
            clip={clip}
            onPatch={(patch) => updateTextClip(selection, patch)}
          />
        )}

        <Placeholder label="Transform" note="position · scale · rotation" />
        <Placeholder label="Opacity" note="0 – 100 %" />
        <Placeholder label="Blending" note="mode · feather" />

        {clip && !isText ? (
          <SpeedControl
            value={clip.speed}
            onCommit={(v) => selection && setClipSpeed(selection, v)}
          />
        ) : (
          <Placeholder label="Speed" note="playback rate · pitch" />
        )}

        {clip && !isText && selection ? (
          <TransitionsControl
            clip={clip}
            onSet={(edge, value) => setClipTransition(selection, edge, value)}
          />
        ) : (
          <Placeholder label="Transitions" note="fade · dissolve" />
        )}
      </div>
    </aside>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="px-3 py-3 border-b"
      style={{ borderColor: "#1a1c20" }}
    >
      <div className="text-xs text-neutral-300 font-medium">{label}</div>
      <div className="mt-2 space-y-1.5">{children}</div>
    </div>
  );
}

function Placeholder({ label, note }: { label: string; note: string }) {
  return (
    <div
      className="px-3 py-3 border-b"
      style={{ borderColor: "#1a1c20" }}
    >
      <div className="text-xs text-neutral-300 font-medium">{label}</div>
      <div className="text-[10px] text-neutral-600 mt-1">{note}</div>
      <div
        className="mt-2 h-8 rounded-[5px] flex items-center justify-center text-[10px] text-neutral-600 uppercase tracking-wider"
        style={{ backgroundColor: "#15171b" }}
      >
        select a clip
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[11px]">
      <span className="text-neutral-500">{label}</span>
      <span className="text-neutral-300 font-mono tabular-nums">{value}</span>
    </div>
  );
}

function SpeedControl({
  value,
  onCommit,
}: {
  value: number;
  onCommit: (v: number) => void;
}) {
  const [draft, setDraft] = useState<string>(value.toString());
  useEffect(() => {
    setDraft(value.toString());
  }, [value]);

  function commit(raw: string) {
    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(value.toString());
      return;
    }
    const clamped = Math.max(0.1, Math.min(10, parsed));
    onCommit(clamped);
    setDraft(clamped.toString());
  }

  return (
    <div
      className="px-3 py-3 border-b"
      style={{ borderColor: "#1a1c20" }}
    >
      <div className="text-xs text-neutral-300 font-medium">Speed</div>
      <div className="text-[10px] text-neutral-600 mt-1">
        playback rate · pitch-preserved audio
      </div>
      <div className="mt-2 flex items-center gap-2">
        <input
          type="range"
          min={0.25}
          max={4}
          step={0.05}
          value={value}
          onChange={(e) => onCommit(Number.parseFloat(e.target.value))}
          className="flex-1 accent-[var(--color-accent)]"
        />
        <input
          type="number"
          min={0.1}
          max={10}
          step={0.05}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
          }}
          className="w-16 px-1.5 py-1 rounded-[5px] text-[11px] text-right font-mono bg-black/40 border outline-none focus:outline-2 focus:outline-offset-1"
          style={{
            borderColor: "#24262c",
            outlineColor: "var(--color-accent)",
            color: "#e5e5e5",
          }}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[9px] text-neutral-600 uppercase tracking-wider">
        <span>0.25×</span>
        <span>1×</span>
        <span>4×</span>
      </div>
    </div>
  );
}

function TextControls({
  clip,
  onPatch,
}: {
  clip: Clip;
  onPatch: (
    patch: Partial<
      Pick<
        Clip,
        "text_content" | "text_color" | "text_font_size" | "text_x" | "text_y"
      >
    >,
  ) => void;
}) {
  return (
    <div className="px-3 py-3 border-b" style={{ borderColor: "#1a1c20" }}>
      <div className="text-xs text-neutral-300 font-medium">Text</div>
      <div className="text-[10px] text-neutral-600 mt-1 mb-2">
        content · colour · size · position
      </div>
      <textarea
        rows={2}
        value={clip.text_content ?? ""}
        onChange={(e) => onPatch({ text_content: e.target.value })}
        className="w-full px-2 py-1.5 rounded-[5px] text-xs border outline-none focus:outline-2 focus:outline-offset-1 resize-none"
        style={{
          backgroundColor: "#0b0c0e",
          borderColor: "#24262c",
          outlineColor: "var(--color-accent)",
          color: "#e5e5e5",
        }}
        placeholder="Your title"
      />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label className="flex items-center gap-1.5 text-[10px] text-neutral-500">
          <span className="shrink-0">colour</span>
          <input
            type="color"
            value={clip.text_color ?? "#ffffff"}
            onChange={(e) => onPatch({ text_color: e.target.value })}
            className="h-6 w-full rounded-[4px] bg-transparent border cursor-pointer"
            style={{ borderColor: "#24262c" }}
          />
        </label>
        <label className="flex items-center gap-1.5 text-[10px] text-neutral-500">
          <span className="shrink-0">size</span>
          <input
            type="number"
            min={8}
            max={256}
            step={2}
            value={clip.text_font_size ?? 64}
            onChange={(e) =>
              onPatch({ text_font_size: Number.parseInt(e.target.value, 10) })
            }
            className="w-full px-1.5 py-1 rounded-[4px] text-[11px] text-right font-mono bg-black/40 border outline-none focus:outline-2 focus:outline-offset-1"
            style={{
              borderColor: "#24262c",
              outlineColor: "var(--color-accent)",
              color: "#e5e5e5",
            }}
          />
        </label>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <PositionSlider
          label="x"
          value={clip.text_x ?? 0.5}
          onChange={(v) => onPatch({ text_x: v })}
        />
        <PositionSlider
          label="y"
          value={clip.text_y ?? 0.5}
          onChange={(v) => onPatch({ text_y: v })}
        />
      </div>
    </div>
  );
}

function TransitionsControl({
  clip,
  onSet,
}: {
  clip: Clip;
  onSet: (edge: "in" | "out", value: ClipTransition | null) => void;
}) {
  return (
    <div className="px-3 py-3 border-b" style={{ borderColor: "#1a1c20" }}>
      <div className="text-xs text-neutral-300 font-medium">Transitions</div>
      <div className="text-[10px] text-neutral-600 mt-1 mb-2">
        fade (to/from black) · dissolve (cross-fade with neighbour)
      </div>
      <TransitionRow
        label="in"
        value={clip.transition_in ?? null}
        onChange={(v) => onSet("in", v)}
      />
      <div className="h-1.5" />
      <TransitionRow
        label="out"
        value={clip.transition_out ?? null}
        onChange={(v) => onSet("out", v)}
      />
    </div>
  );
}

function TransitionRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: ClipTransition | null;
  onChange: (v: ClipTransition | null) => void;
}) {
  const kind = value?.kind ?? "none";
  const frames = value?.duration_frames ?? 12;
  return (
    <div className="flex items-center gap-2">
      <span className="w-6 text-[10px] uppercase tracking-wider text-neutral-500">
        {label}
      </span>
      <select
        value={kind}
        onChange={(e) => {
          const next = e.target.value as "none" | TransitionKind;
          if (next === "none") onChange(null);
          else onChange({ kind: next, duration_frames: frames });
        }}
        className="flex-1 px-1.5 py-1 rounded-[5px] text-[11px] bg-black/40 border outline-none focus:outline-2 focus:outline-offset-1"
        style={{
          borderColor: "#24262c",
          outlineColor: "var(--color-accent)",
          color: "#e5e5e5",
        }}
      >
        <option value="none">none</option>
        <option value="fade">fade</option>
        <option value="dissolve">dissolve</option>
      </select>
      <input
        type="number"
        min={1}
        max={120}
        step={1}
        value={frames}
        disabled={kind === "none"}
        onChange={(e) => {
          if (!value) return;
          const parsed = Number.parseInt(e.target.value, 10);
          const clamped = Math.max(1, Math.min(120, Number.isFinite(parsed) ? parsed : 12));
          onChange({ kind: value.kind, duration_frames: clamped });
        }}
        className="w-14 px-1.5 py-1 rounded-[5px] text-[11px] text-right font-mono bg-black/40 border outline-none focus:outline-2 focus:outline-offset-1 disabled:opacity-40"
        style={{
          borderColor: "#24262c",
          outlineColor: "var(--color-accent)",
          color: "#e5e5e5",
        }}
        title="Duration in frames (1–120)"
      />
      <span className="text-[9px] text-neutral-600 uppercase tracking-wider">
        f
      </span>
    </div>
  );
}

function PositionSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-[10px] text-neutral-500">
      <div className="flex items-center justify-between">
        <span>{label}</span>
        <span className="text-neutral-400 font-mono tabular-nums">
          {Math.round(value * 100)}%
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(e) => onChange(Number.parseFloat(e.target.value))}
        className="accent-[var(--color-accent)]"
      />
    </label>
  );
}
