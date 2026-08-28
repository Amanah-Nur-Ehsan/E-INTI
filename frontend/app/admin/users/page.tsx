"use client";

import { useState, type FormEvent } from "react";
import { RedirectTo } from "@/components/auth/RedirectTo";
import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  useAdminUsers,
  useDeleteUser,
  useResetUserPassword,
  useSession,
  useUpdateUser,
  type UpdateUserAdminRequest,
  type UserAdminRead,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

/** User management (admin-only, server-gated by require_any_admin). */
export default function AdminUsersPage() {
  const { data: session, isLoading } = useSession();
  const { data: users } = useAdminUsers();
  const updateUser = useUpdateUser();
  const resetPassword = useResetUserPassword();
  const deleteUser = useDeleteUser();

  const [resetFor, setResetFor] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const [editing, setEditing] = useState<UserAdminRead | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editAddress, setEditAddress] = useState("");
  const [editAffiliation, setEditAffiliation] = useState("");
  const [editBio, setEditBio] = useState("");
  const [editRole, setEditRole] = useState<"user" | "admin">("user");
  const [editActive, setEditActive] = useState(true);

  const mutationError = updateUser.error ?? resetPassword.error ?? deleteUser.error;

  if (isLoading) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-8" />;
  }
  if (!session?.authenticated || session.role !== "admin") {
    return <RedirectTo to="/" />;
  }

  function openEdit(user: UserAdminRead) {
    setEditing(user);
    setEditName(user.full_name ?? "");
    setEditEmail(user.email);
    setEditPhone(user.phone ?? "");
    setEditAddress(user.address ?? "");
    setEditAffiliation(user.affiliation ?? "");
    setEditBio(user.bio ?? "");
    setEditRole(user.role === "admin" ? "admin" : "user");
    setEditActive(user.is_active);
  }

  function handleEditSubmit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const isSelf = editing.email === session?.email;
    const body: UpdateUserAdminRequest = {};
    if (editName !== (editing.full_name ?? "")) body.full_name = editName;
    if (editEmail !== editing.email) body.email = editEmail;
    if (editPhone !== (editing.phone ?? "")) body.phone = editPhone;
    if (editAddress !== (editing.address ?? "")) body.address = editAddress;
    if (editAffiliation !== (editing.affiliation ?? "")) body.affiliation = editAffiliation;
    if (editBio !== (editing.bio ?? "")) body.bio = editBio;
    if (!isSelf && editRole !== editing.role) body.role = editRole;
    if (!isSelf && editActive !== editing.is_active) body.is_active = editActive;
    updateUser.mutate({ userId: editing.id, body }, { onSuccess: () => setEditing(null) });
  }

  const editingSelf = editing?.email === session?.email;

  return (
    <DashboardShell>
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Users</h1>
          <p className="text-sm text-muted-foreground">Manage user accounts.</p>
        </div>

        {!editing && mutationError && (
          <p className="text-sm text-destructive" role="alert">
            {(mutationError as Error).message}
          </p>
        )}

        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((user) => (
                <tr key={user.id} className="border-b last:border-0">
                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">{user.full_name || user.email}</p>
                    <p className="text-xs text-muted-foreground">{user.email}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        user.role === "admin"
                          ? "bg-red-100 text-red-800"
                          : "bg-zinc-100 text-zinc-600",
                      )}
                    >
                      {user.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={user.is_active ? "text-green-700" : "text-red-600"}>
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <Button size="sm" variant="outline" onClick={() => openEdit(user)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          updateUser.mutate({ userId: user.id, body: { is_active: !user.is_active } })
                        }
                      >
                        {user.is_active ? "Deactivate" : "Activate"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setResetFor(resetFor === user.id ? null : user.id);
                          setNewPassword("");
                        }}
                      >
                        Reset password
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => {
                          if (window.confirm(`Delete ${user.email}? This cannot be undone.`)) {
                            deleteUser.mutate(user.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                    {resetFor === user.id && (
                      <form
                        className="mt-2 flex items-center justify-end gap-2"
                        onSubmit={(e) => {
                          e.preventDefault();
                          resetPassword.mutate({ userId: user.id, newPassword });
                          setResetFor(null);
                        }}
                      >
                        <input
                          type="password"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="New password (min 8 chars)"
                          minLength={8}
                          required
                          autoFocus
                          className="w-56 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground"
                        />
                        <Button size="sm" type="submit" disabled={newPassword.length < 8}>
                          Set
                        </Button>
                      </form>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!users?.length && (
            <p className="px-4 py-6 text-sm text-muted-foreground">No users yet.</p>
          )}
        </Card>
      </div>

      {/* Edit user modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md p-4">
            <h2 className="text-lg font-semibold text-foreground">Edit user</h2>
            <form className="mt-4 flex flex-col gap-4" onSubmit={handleEditSubmit}>
              <label className="block">
                <span className="text-sm font-medium text-foreground">Name</span>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-foreground">Email</span>
                <input
                  type="email"
                  required
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                />
              </label>

              <div className="space-y-4 border-t border-red-100 pt-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Contact & affiliation
                </p>
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Phone</span>
                  <input
                    type="tel"
                    value={editPhone}
                    onChange={(e) => setEditPhone(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Address</span>
                  <input
                    type="text"
                    value={editAddress}
                    onChange={(e) => setEditAddress(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Affiliation</span>
                  <input
                    type="text"
                    value={editAffiliation}
                    onChange={(e) => setEditAffiliation(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Bio</span>
                  <textarea
                    value={editBio}
                    onChange={(e) => setEditBio(e.target.value)}
                    rows={3}
                    className="mt-1.5 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                  />
                </label>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Role</span>
                  <select
                    value={editRole}
                    disabled={editingSelf}
                    onChange={(e) => setEditRole(e.target.value as "user" | "admin")}
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground disabled:opacity-50"
                  >
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-foreground">Status</span>
                  <select
                    value={String(editActive)}
                    disabled={editingSelf}
                    onChange={(e) => setEditActive(e.target.value === "true")}
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground disabled:opacity-50"
                  >
                    <option value="true">active</option>
                    <option value="false">inactive</option>
                  </select>
                </label>
              </div>

              {updateUser.isError && (
                <p className="text-sm text-destructive" role="alert">
                  {(updateUser.error as Error).message}
                </p>
              )}

              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={updateUser.isPending}>
                  {updateUser.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </DashboardShell>
  );
}
