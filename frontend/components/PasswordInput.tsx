"use client";

import { useState, type ComponentProps } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

/** A password input with an eye toggle to show/hide the value. */
export function PasswordInput({
  className,
  containerClassName,
  ...props
}: ComponentProps<"input"> & { containerClassName?: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className={cn("relative", containerClassName)}>
      <input
        type={visible ? "text" : "password"}
        {...props}
        className={cn(className, "pr-10")}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
      >
        {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}
