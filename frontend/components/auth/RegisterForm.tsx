"use client";
import { AuthBrandMark } from "@/components/auth/AuthBrandMark";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/PasswordInput";
import { useRegister } from "@/lib/api/hooks";

export function RegisterForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [affiliation, setAffiliation] = useState("");
  const [bio, setBio] = useState("");
  const register = useRegister();

  return (
    <div className="w-full">
      <AuthBrandMark />
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#0C2D48] lg:mt-0">
        Create account
      </h2>
      <p className="mt-1.5 text-sm text-slate-500">
        You&apos;ll receive an email with a link to activate your account.
      </p>

      <form
        className="mt-7 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          register.mutate(
            { email, password, full_name: name, phone, address, affiliation, bio },
            { onSuccess: () => router.push(`/login?registered=${encodeURIComponent(email)}`) },
          );
        }}
      >
        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Name</span>
          <input
            type="text"
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@university.edu"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-[#1E3A5F]">Password</span>
          <PasswordInput
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
          />
        </label>

        <div className="mt-1 border-t border-red-100 pt-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Optional details</p>
          <div className="mt-3 flex flex-col gap-4">
            <label className="block">
              <span className="text-sm font-medium text-[#1E3A5F]">Phone</span>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="Phone number"
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-[#1E3A5F]">Address</span>
              <input
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Address"
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-[#1E3A5F]">Affiliation</span>
              <input
                type="text"
                value={affiliation}
                onChange={(e) => setAffiliation(e.target.value)}
                placeholder="Institution or affiliation"
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-[#1E3A5F]">Bio</span>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder="Short bio"
                rows={3}
                className="mt-1.5 w-full resize-none rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
              />
            </label>
          </div>
        </div>

        {register.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(register.error as Error).message}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          disabled={!name || !email || !password || password.length < 8 || register.isPending}
          className="h-11 rounded-lg bg-red-600 text-white shadow-sm hover:bg-red-700 focus-visible:ring-red-300"
        >
          {register.isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <div className="mt-4 text-sm">
        <Link
          href="/login"
          className="font-medium text-red-600 hover:text-red-700 hover:underline"
        >
          Already have an account? Sign in
        </Link>
      </div>
    </div>
  );
}
