"use client";

/**
 * Sohbet ve görüşme sayfaları kiminle konuşulduğunu adresten alır:
 *   ?karakter=<id>  Karakter Stüdyosu'ndaki bir karakter
 *   ?miras=<id>     bir Miras personası (sahibin önizlemesi ya da alıcı)
 *   (hiçbiri)       EVA
 */

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getCharacter, listPersonas, type Character } from "@/lib/api/client";

export type PersonaParam = {
  personaId: string | null;
  kind: "eva" | "character" | "legacy";
  name: string;
  character: Character | null;
  failed: boolean;
};

export function usePersonaParam(): PersonaParam {
  const params = useSearchParams();
  const characterId = params.get("karakter");
  const legacyId = params.get("miras");
  const personaId = characterId ?? legacyId;
  const kind = characterId ? "character" : legacyId ? "legacy" : "eva";
  const [loaded, setLoaded] = useState<{ id: string; name: string; character: Character | null }>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!personaId) return;
    let cancelled = false;
    const load = characterId
      ? getCharacter(characterId).then((c) => ({ id: c.id, name: c.name, character: c }))
      : listPersonas().then((list) => {
          const p = list.find((x) => x.id === personaId);
          if (!p) throw new Error("persona not visible");
          return { id: p.id, name: p.name, character: null };
        });
    load
      .then((value) => {
        if (!cancelled) setLoaded(value);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [personaId, characterId]);

  const current = loaded && loaded.id === personaId ? loaded : undefined;
  return {
    personaId,
    kind,
    name: personaId ? (current?.name ?? "") : "EVA",
    character: current?.character ?? null,
    failed,
  };
}
