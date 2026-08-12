"use client";

import { useLang } from "@/lib/i18n-context";
import { Button } from "@/components/ui/button";

export function LanguageSwitcher() {
  const { lang, setLang } = useLang();

  function toggle() {
    setLang(lang === "es" ? "en" : "es");
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggle}
      className="h-7 px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
    >
      {lang === "es" ? "EN" : "ES"}
    </Button>
  );
}
