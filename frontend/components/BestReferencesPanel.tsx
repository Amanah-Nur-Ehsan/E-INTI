"use client";

import { ReferenceCard } from "@/components/ReferenceCard";
import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/api/client";
import { useBestReferences } from "@/lib/api/hooks";

/** The ranked shortlist of INTI references this paper should cite -- up to
 * 5 for the whole paper, not one per claim. An empty list (analysis ran
 * but found nothing usable) and "not ready yet" (404, analysis hasn't
 * produced recommendations) are different states and read differently. */
export function BestReferencesPanel({
  draftId,
  enabled,
}: {
  draftId: string;
  enabled: boolean;
}) {
  const { data, error, isLoading } = useBestReferences(draftId, enabled);

  if (!enabled) return null;

  if (error) {
    // 404 means no recommendations exist at all yet for this draft, not a
    // real error -- everything else is worth surfacing.
    if (error instanceof ApiError && error.status === 404) {
      return (
        <Card className="p-4">
          <p className="text-sm text-muted-foreground">
            No supporting references were found in the library for this paper.
          </p>
        </Card>
      );
    }
    return (
      <Card className="p-4">
        <p className="text-sm text-destructive">Could not load recommended references.</p>
      </Card>
    );
  }

  if (isLoading || !data) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">Loading recommended references…</p>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted-foreground">
          No supporting references were found in the library for this paper.
        </p>
      </Card>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-medium text-foreground">
        Recommended references ({data.length})
      </h2>
      {data.map((item) => (
        <ReferenceCard key={item.reference.id} draftId={draftId} item={item} />
      ))}
    </section>
  );
}
