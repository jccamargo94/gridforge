"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { t as translate, type Lang } from "./i18n";

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function resolveLang(): Lang {
  if (typeof window === "undefined") return "es";
  const stored = localStorage.getItem("gridforge-lang");
  if (stored === "es" || stored === "en") return stored;
  return "es";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(resolveLang);

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem("gridforge-lang", l);
  };

  return (
    <I18nContext.Provider value={{ lang, setLang, t: (key: string) => translate(lang, key) }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useT() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useT must be used within I18nProvider");
  return ctx.t;
}

export function useLang() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useLang must be used within I18nProvider");
  return { lang: ctx.lang, setLang: ctx.setLang };
}
