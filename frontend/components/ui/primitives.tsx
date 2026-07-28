import type { ButtonHTMLAttributes, HTMLAttributes } from "react";

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("rounded-lg border border-zinc-200 bg-white shadow-sm", className)}
      {...props}
    />
  );
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
}) {
  const variants = {
    primary: "bg-zinc-900 text-white hover:bg-zinc-700 disabled:bg-zinc-300",
    secondary: "bg-white text-zinc-900 border border-zinc-300 hover:bg-zinc-50",
    danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
    ghost: "bg-transparent text-zinc-600 hover:bg-zinc-100",
  };
  const sizes = {
    sm: "px-2.5 py-1 text-xs",
    md: "px-4 py-2 text-sm",
  };
  return (
    <button
      className={cx(
        "rounded-md font-medium transition-colors disabled:cursor-not-allowed",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "green" | "yellow" | "orange" | "red" | "blue" | "gray";
}) {
  const tones = {
    neutral: "bg-zinc-100 text-zinc-700",
    green: "bg-emerald-100 text-emerald-800",
    yellow: "bg-amber-100 text-amber-900",
    orange: "bg-orange-100 text-orange-900",
    red: "bg-red-100 text-red-800",
    blue: "bg-sky-100 text-sky-800",
    gray: "bg-zinc-100 text-zinc-500",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx("animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
