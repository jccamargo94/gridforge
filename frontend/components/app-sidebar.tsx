"use client";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import { cn } from "@/lib/utils";
import { Gauge, GitCompareArrows, Layers, LogOut, Network } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { GridForgeLogoFull } from "@/components/gridforge-logo";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV_ITEMS = [
  { href: "/runs", labelKey: "sidebar.runs", icon: Gauge },
  { href: "/scenarios", labelKey: "sidebar.scenarios", icon: Layers },
  { href: "/compare", labelKey: "sidebar.compare", icon: GitCompareArrows },
  { href: "/nodal", labelKey: "sidebar.nodal", icon: Network },
] as const;

export function AppSidebar() {
  const pathname = usePathname();
  const { signOut } = useAuth();
  const t = useT();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-sidebar-border bg-sidebar px-4 py-6 md:flex">
      <div className="mb-8">
        <GridForgeLogoFull />
      </div>
      <nav className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
          const active = href === "/nodal" ? pathname?.includes("/nodal") : pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors border-l-2",
                active
                  ? "bg-amber-500/10 text-amber-400 border-l-amber-500"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground border-l-transparent"
              )}
            >
              <Icon className="size-4" />
              {t(labelKey)}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto space-y-2">
        <div className="flex items-center justify-between px-3">
          <span className="text-xs text-muted-foreground">{t("sidebar.theme")}</span>
          <ThemeToggle />
        </div>
        <LanguageSwitcher />
      </div>
      <Button
        variant="ghost"
        className="justify-start gap-2 text-muted-foreground hover:text-foreground"
        onClick={() => signOut()}
      >
        <LogOut className="size-4" />
        {t("sidebar.signOut")}
      </Button>
    </aside>
  );
}
