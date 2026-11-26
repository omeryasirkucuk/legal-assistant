"use client";

import { useEffect } from "react";

export function useKeyboardViewport() {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;

    const style = document.documentElement.style;
    const property = "--keyboard-viewport-height";
    const update = () => {
      // Safari can shrink the visual viewport for the keyboard while keeping the layout viewport.
      if (viewport.scale === 1 && window.innerHeight - viewport.height > 80) {
        style.setProperty(property, `${Math.floor(viewport.height)}px`);
      } else {
        style.removeProperty(property);
      }
    };

    update();
    viewport.addEventListener("resize", update);
    window.addEventListener("resize", update);
    return () => {
      viewport.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
      style.removeProperty(property);
    };
  }, []);
}
