"use client";

// Whether the screen is wide enough for the sidebar beside the page (Tailwind's md, 768px).
// Below it, the sidebar is a drawer over the page and side panels take the whole screen.
import { useEffect, useState } from "react";

const QUERY = "(min-width: 768px)";

export function useWide(): boolean {
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setWide(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return wide;
}
