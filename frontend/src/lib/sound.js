export const playChaChing = () => {
  try {
    const audio = new Audio("/chaching.wav");
    audio.volume = 0.7;
    audio.play().catch(() => {});
  } catch {}
};
