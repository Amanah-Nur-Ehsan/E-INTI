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
  // SdgSummary only mounts once analysis has completed, so classification
  // has definitely run by the time this renders. A missing sdgNumber with
  // a rationale present means the classifier looked at all 17 goals and
  // genuinely found none that fit -- that's a real, informative outcome,
  // not a loading state, so it gets its own message instead of vanishing
  // silently (see sdg_classification_service.py's `fits` field).
  if (!sdgNumber) {
    if (!sdgRationale) return null;
    return (
      <Card className="p-3">
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="outline" className="bg-gray-100 text-gray-700 border-gray-200">
            No SDG matched
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{sdgRationale}</p>
      </Card>
    );
  }

  return (
    <Card className="p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" className="bg-blue-100 text-blue-800 border-blue-200">
          SDG {sdgNumber}
        </Badge>
        {sdgName && (
          <span className="flex items-center gap-1 text-foreground">
            {sdgName}
            <CopyButton text={sdgName} />
          </span>
        )}
        {sdgKeyword && (
          <span className="flex items-center gap-1 text-muted-foreground">
            · {sdgKeyword}
            <CopyButton text={sdgKeyword} />
          </span>
        )}
      </div>
      {sdgRationale && (
        <p className="mt-1 flex items-start gap-1 text-xs text-muted-foreground">
          <span>{sdgRationale}</span>
          <CopyButton text={sdgRationale} />
        </p>
      )}
    </Card>
  );
}
