"use client";

import { useEffect, useState } from "react";
import { characterFaceUrl } from "@/lib/api/client";

/** Karakterin yüz görseli; yoksa adının baş harfi. Görsel korumalı uçtan geçici blob olarak gelir. */
export function CharacterFace({
  id,
  name,
  hasFace,
  className = "h-12 w-12 rounded-full",
}: {
  id: string;
  name: string;
  hasFace: boolean;
  className?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!hasFace) return;
    let url: string | null = null;
    let cancelled = false;
    characterFaceUrl(id)
      .then((u) => {
        url = u;
        if (!cancelled) setSrc(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      setSrc(null);
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, hasFace]);

  if (hasFace && src) {
    // eslint-disable-next-line @next/next/no-img-element -- korumalı uçtan gelen geçici blob adresi
    return <img src={src} alt="" className={`${className} object-cover`} />;
  }
  return (
    <span
      className={`${className} flex shrink-0 items-center justify-center bg-gradient-to-br from-accent to-accent-2 text-sm font-bold`}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}
