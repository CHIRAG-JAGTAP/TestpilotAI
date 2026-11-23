import { useEffect, useState } from "react";
import { dbHealth } from "../services/api";

export default function StatusBadge() {
  const [state, setState] = useState<"checking" | "ok" | "down">("checking");
  useEffect(() => {
    dbHealth().then(h => setState(h.connected && h.integrity.ok ? "ok" : "down")).catch(() => setState("down"));
  }, []);
  const label = { checking: "Checking backend…", ok: "Backend + database OK", down: "Backend not reachable (start uvicorn)" }[state];
  return <span className={`badge ${state}`}>{label}</span>;
}
