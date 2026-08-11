"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAdminLogin } from "@/lib/api/hooks";

export function AdminLogin() {
  const [password, setPassword] = useState("");
  const login = useAdminLogin();

  return (
    <Card className="mx-auto mt-16 w-full max-w-sm p-4">
      <h1 className="text-sm font-medium text-foreground">Admin login</h1>
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate(password);
        }}
      >
        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground"
        />
        <Button type="submit" size="sm" disabled={!password || login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
        {login.isError && (
          <p className="text-xs text-destructive">{(login.error as Error).message}</p>
        )}
      </form>
    </Card>
  );
}
