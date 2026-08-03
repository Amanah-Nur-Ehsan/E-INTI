"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Small icon button that copies `text` to the clipboard and flashes a
 * checkmark for a second as feedback -- used anywhere a value (an SDG
 * keyword, a citation string, a rewritten paragraph) needs to be pasted
 * elsewhere without retyping it. */
export function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className="h-6 gap-1 px-1.5 text-xs text-muted-foreground"
      onClick={handleCopy}
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {label ?? (copied ? "Copied" : "Copy")}
    </Button>
  );
}
