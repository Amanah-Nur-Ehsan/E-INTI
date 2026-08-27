import { Suspense } from "react";
import { ActivateForm } from "@/components/auth/ActivateForm";
import { AuthShell } from "@/components/auth/AuthShell";

export default function ActivatePage() {
  return (
    <AuthShell>
      <Suspense fallback={null}>
        <ActivateForm />
      </Suspense>
    </AuthShell>
  );
}
