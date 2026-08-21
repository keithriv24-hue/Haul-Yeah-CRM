import React, { useEffect, useRef, useState } from "react";
import axios from "axios";

const HEALTH_URL = `${process.env.REACT_APP_BACKEND_URL}/api/health`;

export const UpdateOverlay = () => {
  const [down, setDown] = useState(false);
  const failsRef = useRef(0);
  const wasDownRef = useRef(false);

  useEffect(() => {
    let stop = false;
    let timer;
    const check = async () => {
      try {
        await axios.get(HEALTH_URL, { timeout: 6000 });
        if (stop) return;
        failsRef.current = 0;
        if (wasDownRef.current) {
          window.location.reload();
          return;
        }
        setDown(false);
        timer = setTimeout(check, 25000);
      } catch (e) {
        if (stop) return;
        const status = e?.response?.status;
        if (!e.response || [502, 503, 504].includes(status)) {
          failsRef.current += 1;
          if (failsRef.current >= 2) {
            wasDownRef.current = true;
            setDown(true);
          }
        }
        timer = setTimeout(check, 5000);
      }
    };
    check();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, []);

  if (!down) return null;
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  return (
    <div data-testid="update-overlay" className="fixed inset-0 z-[100] bg-primary/95 backdrop-blur-sm flex items-center justify-center px-6">
      <div className="text-center max-w-sm">
        <img src="/logo.png" alt="Haul Yeah Moving" className="w-40 mx-auto rounded-lg" />
        <div className="mt-6 flex justify-center">
          <span className="w-8 h-8 border-[3px] border-white/20 border-t-accent rounded-full animate-spin" />
        </div>
        <h1 data-testid="update-overlay-title" className="text-white font-bold text-lg mt-5">
          {offline ? "You're offline" : "The website is updating"}
        </h1>
        <p className="text-white/60 text-sm mt-2">
          {offline
            ? "Check your connection — we'll reconnect automatically."
            : "Hang tight, this usually takes about a minute. We'll bring you right back when it's done."}
        </p>
      </div>
    </div>
  );
};
