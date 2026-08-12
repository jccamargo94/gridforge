"use client";

import { GridForgeLogoMark } from "@/components/gridforge-logo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/lib/i18n-context";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const t = useT();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError(t("resetPassword.passwordsDontMatch"));
      return;
    }
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setError(error.message);
      return;
    }
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm border-border bg-card shadow-lg">
        <div className="p-8 flex flex-col items-center text-center">
          <GridForgeLogoMark className="size-10 text-amber-500 mb-4" />
          <h1 className="text-xl font-bold text-foreground">{t("resetPassword.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("resetPassword.subtitle")}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex w-full flex-col gap-4">
            <div className="flex flex-col gap-1.5 text-left">
              <Label htmlFor="password" className="text-sm font-medium text-foreground">
                {t("resetPassword.newPassword")}
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

            <div className="flex flex-col gap-1.5 text-left">
              <Label htmlFor="confirm_password" className="text-sm font-medium text-foreground">
                {t("resetPassword.confirmPassword")}
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
              {t("resetPassword.save")}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
