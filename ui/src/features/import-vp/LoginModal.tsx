import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { vpLogin, type VPAccount } from "../../api/importVp";

interface Props {
  defaultBaseUrl?: string;
  onClose: () => void;
  onSuccess?: (account: VPAccount) => void;
}

export default function LoginModal({ defaultBaseUrl, onClose, onSuccess }: Props) {
  const qc = useQueryClient();
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: vpLogin,
    onSuccess: (acc) => {
      qc.setQueryData(["vp-account"], acc);
      qc.invalidateQueries({ queryKey: ["vp-account"] });
      onSuccess?.(acc);
      onClose();
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    login.mutate({ base_url: baseUrl, email, password });
  }

  const errDetail =
    login.error && typeof login.error === "object" && "response" in login.error
      ? (login.error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      : undefined;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-[9px] border p-6"
        style={{ backgroundColor: "#141519", borderColor: "#24262c" }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-neutral-100">
            Connect to Video Planner
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-500 hover:text-neutral-200 rounded-[5px] p-1"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <Field
            label="Server"
            value={baseUrl}
            onChange={setBaseUrl}
            placeholder="http://localhost:8000"
            autoComplete="url"
          />
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            required
          />
        </div>

        {errDetail && (
          <p className="mt-3 text-xs text-red-400 break-words">{errDetail}</p>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-2 text-sm text-neutral-400 rounded-[7px] hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={login.isPending}
            className="px-4 py-2 text-sm font-medium rounded-[7px] active:scale-[0.98] disabled:opacity-50"
            style={{ backgroundColor: "var(--color-accent)", color: "#0b0c0e" }}
          >
            {login.isPending ? "Connecting…" : "Log in"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs uppercase tracking-wider text-neutral-500">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        className="mt-1 w-full rounded-[7px] px-3 py-2 text-sm text-neutral-100 border outline-none focus:outline-2 focus:outline-offset-2"
        style={{
          backgroundColor: "#0b0c0e",
          borderColor: "#24262c",
          outlineColor: "var(--color-accent)",
        }}
      />
    </label>
  );
}
