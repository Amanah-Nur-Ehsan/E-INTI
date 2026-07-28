"use client";

import Link from "next/link";
import { useState } from "react";
import { useCreateProject, useProjects } from "@/lib/api/hooks";
import { Button, Card, Spinner } from "@/components/ui/primitives";

export default function ProjectsPage() {
  const { data: projects, isLoading } = useProjects();
  const createProject = useCreateProject();
  const [name, setName] = useState("");
  const [fieldOfStudy, setFieldOfStudy] = useState("");

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await createProject.mutateAsync({
      name: name.trim(),
      field_of_study: fieldOfStudy.trim() || null,
      citation_style: "APA",
    });
    setName("");
    setFieldOfStudy("");
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold text-zinc-900">Projects</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Each project pairs one draft paper with one uploaded reference dataset.
      </p>

      <Card className="mt-6 p-5">
        <form onSubmit={handleCreate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-zinc-600" htmlFor="project-name">
              Project name
            </label>
            <input
              id="project-name"
              className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="e.g. Respiratory sound classification paper"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-zinc-600" htmlFor="project-field">
              Field of study (optional)
            </label>
            <input
              id="project-field"
              className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              placeholder="e.g. Health and Life Sciences"
              value={fieldOfStudy}
              onChange={(event) => setFieldOfStudy(event.target.value)}
            />
          </div>
          <Button type="submit" disabled={createProject.isPending || !name.trim()}>
            {createProject.isPending ? <Spinner className="h-4 w-4" /> : "Create project"}
          </Button>
        </form>
        {createProject.isError && (
          <p className="mt-2 text-xs text-red-600">{(createProject.error as Error).message}</p>
        )}
      </Card>

      <div className="mt-8">
        {isLoading ? (
          <div className="flex justify-center py-10 text-zinc-400">
            <Spinner className="h-6 w-6" />
          </div>
        ) : !projects || projects.length === 0 ? (
          <p className="py-10 text-center text-sm text-zinc-500">
            No projects yet -- create one above to get started.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {projects.map((project) => (
              <li key={project.id}>
                <Link href={`/projects/${project.id}`}>
                  <Card className="flex items-center justify-between p-4 transition-colors hover:border-zinc-300 hover:bg-zinc-50">
                    <div>
                      <p className="font-medium text-zinc-900">{project.name}</p>
                      <p className="text-xs text-zinc-500">
                        {project.field_of_study ?? "No field of study set"} &middot;{" "}
                        {project.citation_style}
                      </p>
                    </div>
                    <span className="text-zinc-400">&rarr;</span>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
