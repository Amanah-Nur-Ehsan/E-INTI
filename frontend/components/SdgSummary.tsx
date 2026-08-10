"use client";

import { CopyButton } from "@/components/CopyButton";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

/** The paper's classified SDG -- describes the whole draft, not any one
 * reference, so it sits above the reference shortlist rather than inside
 * it (it used to live inside the single-reference panel, back when there
 * was only one reference to attach it to). */
export function SdgSummary({
  sdgNumber,
  sdgName,
  sdgKeyword,
  sdgRationale,
}: {
  sdgNumber: number | null | undefined;
  sdgName: string | null | undefined;
  sdgKeyword: string | null | undefined;
  sdgRationale: string | null | undefined;
}) {
  if (!sdgNumber) return null;

  return (
    <Card className="p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className="bg-blue-100 text-blue-800 border-blue-200">
          SDG {sdgNumber}
        </Badge>
        <span className="text-foreground">{sdgName}</span>
        {sdgKeyword && (
          <span className="flex items-center gap-1 text-muted-foreground">
            · {sdgKeyword}
            <CopyButton text={sdgKeyword} />
          </span>
        )}
      </div>
      {sdgRationale && <p className="mt-1 text-xs text-muted-foreground">{sdgRationale}</p>}
    </Card>
  );
}
