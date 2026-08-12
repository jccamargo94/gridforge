"use client";

import { GridForgeLogoFull, GridForgeLogoMark } from "@/components/gridforge-logo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n-context";
import { supabase } from "@/lib/supabase";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const t = useT();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError(t("signup.passwordsDontMatch"));
      return;
    }
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) {
      setError(error.message);
      return;
    }
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row bg-background">
      {/* Left: Branding */}
      <div
        className={cn(
          "relative flex flex-col items-center justify-center overflow-hidden px-8 py-12 md:w-2/5 md:py-0",
          "bg-[#09090b]",
        )}
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(245,158,11,0.06) 39px, rgba(245,158,11,0.06) 40px), repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(245,158,11,0.06) 39px, rgba(245,158,11,0.06) 40px)",
        }}
      >
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <GridForgeLogoMark className="size-80 text-amber-500/5" />
        </div>
        <div className="relative z-10 flex flex-col items-center text-center">
          <GridForgeLogoFull className="mb-6 [&_svg]:size-12 [&_p:first-child]:text-2xl [&_p:last-child]:text-[11px]" />
          <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
            Professional Energy Dispatch Modeling For The Colombian Power Grid
          </p>
        </div>
      </div>

      {/* Right: Form */}
      <div className="flex flex-1 items-center justify-center px-4 py-12 md:px-8">
        <Card className="w-full max-w-md border-border bg-card shadow-lg">
          <div className="p-8">
            <h1 className="text-2xl font-bold text-foreground">{t("signup.title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("signup.subtitle")}
            </p>

            <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email" className="text-sm font-medium text-foreground">
                  {t("signup.email")}
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="bg-background border-input"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password" className="text-sm font-medium text-foreground">
                  {t("signup.password")}
                </Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="bg-background border-input"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="confirm_password" className="text-sm font-medium text-foreground">
                  {t("signup.confirmPassword")}
                </Label>
                <Input
                  id="confirm_password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={6}
                  className="bg-background border-input"
                />
              </div>

              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full bg-amber-500 text-black hover:bg-amber-400">
                {t("signup.createAccount")}
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-muted-foreground">
              {t("signup.hasAccount")}{" "}
              <Link href="/login" className="font-medium text-amber-500 hover:text-amber-400">
                {t("signup.signIn")}
              </Link>
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}
