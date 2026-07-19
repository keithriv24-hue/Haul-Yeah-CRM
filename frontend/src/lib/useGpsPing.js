import { useEffect } from "react";
import { gpsPingApi, myTimeApi } from "@/lib/api";
import { getPosition } from "@/lib/geo";

export default function useGpsPing(role) {
  useEffect(() => {
    if (role !== "crew") return;
    let stop = false;
    const ping = async () => {
      try {
        const t = await myTimeApi();
        if (stop || !t.clocked_in) return;
        const pos = await getPosition();
        if (pos && !stop) await gpsPingApi(pos);
      } catch {
        /* clocked out or offline — skip */
      }
    };
    ping();
    const id = setInterval(ping, 4 * 60 * 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [role]);
}
