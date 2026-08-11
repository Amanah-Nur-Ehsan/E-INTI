"use client";

import { cn } from "@/lib/utils";

/** Shared by the public draft-upload flow and the admin library/DOI/PDF
 * panels -- a plain styled file input, no drag-and-drop, no preview. */
export function FilePicker({
  file,
  onSelect,
  disabled,
  accept,
}: {
  file: File | null;
  onSelect: (file: File | null) => void;
  disabled?: boolean;
  accept: string;
}) {
  return (
    <>
      <label
        className={cn(
          "rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium text-foreground",
          disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-muted",
        )}
      >
        Choose file
        <input
          type="file"
          accept={accept}
          className="sr-only"
          disabled={disabled}
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </label>
      <span className="text-xs text-muted-foreground">{file ? file.name : "No file chosen"}</span>
    </>
  );
}
