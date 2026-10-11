import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUsers, createUser, updateUser, updateUserStatus } from "@/api/users";
import { getOrganizations } from "@/api/platform";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { useAuth } from "@/store/useAuth";
import type { UserRecord } from "@/types/auth";

export function Users() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "superadmin";

  const [selectedOrgFilter, setSelectedOrgFilter] = useState<string>("");
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);

  // Form states
  const [newUserName, setNewUserName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState("org_admin");
  const [newUserOrgId, setNewUserOrgId] = useState("");

  const [editRole, setEditRole] = useState("org_admin");
  const [editOrgId, setEditOrgId] = useState("");

  // Error/Success state
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Queries
  const { data: orgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });

  const { data: users, isLoading: loadingUsers, isError: usersError } = useQuery({
    queryKey: ["usersList", selectedOrgFilter],
    queryFn: () => getUsers(selectedOrgFilter || undefined),
  });

  // Create User Mutation
  const createUserMutation = useMutation({
    mutationFn: () =>
      createUser({
        name: newUserName,
        email: newUserEmail,
        password: newUserPassword,
        role: newUserRole,
        organization_id: isSuperAdmin ? newUserOrgId || null : user?.organization_id || null,
      }),
    onSuccess: (newUser) => {
      queryClient.invalidateQueries({ queryKey: ["usersList"] });
      setShowCreateModal(false);
      setNewUserName("");
      setNewUserEmail("");
      setNewUserPassword("");
      setSuccessMsg(`User '${newUser.name}' created successfully.`);
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to create user"),
  });

  // Update User Mutation
  const updateUserMutation = useMutation({
    mutationFn: (targetUser: UserRecord) =>
      updateUser(targetUser.id, {
        role: editRole,
        organization_id: isSuperAdmin ? editOrgId || null : targetUser.organization_id,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["usersList"] });
      setEditingUser(null);
      setSuccessMsg("User updated successfully.");
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to update user"),
  });

  // Toggle User Status Mutation
  const toggleStatusMutation = useMutation({
    mutationFn: ({ userId, isCurrentlyActive }: { userId: string; isCurrentlyActive: boolean }) =>
      updateUserStatus(userId, !isCurrentlyActive),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["usersList"] });
      setSuccessMsg(`User account ${data.is_active ? "activated" : "deactivated"} successfully.`);
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to change user status"),
  });

  if (loadingUsers) return <LoadingState />;
  if (usersError) return <ErrorState message="Failed to load enterprise users." />;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Users & Roles Management</h1>
          <p className="page-description">
            Manage organization administrators, user roles, security scopes, and active access credentials.
          </p>
        </div>

        {isSuperAdmin && orgs && orgs.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Filter Organization:</span>
            <select
              value={selectedOrgFilter}
              onChange={(e) => setSelectedOrgFilter(e.target.value)}
              style={{
                background: "var(--surface-raised)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                padding: "6px 12px",
                fontSize: "13px",
              }}
            >
              <option value="">All Organizations</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name} ({o.code})
                </option>
              ))}
            </select>
          </div>
        )}
      </header>

      {errorMsg && (
        <div style={{ padding: "12px", background: "var(--danger-bg)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--danger)", borderRadius: "6px", marginBottom: "16px" }}>
          {errorMsg}
          <button onClick={() => setErrorMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--danger)" }}>✕</button>
        </div>
      )}

      {successMsg && (
        <div style={{ padding: "12px", background: "var(--success-bg)", border: "1px solid rgba(70,189,146,0.3)", color: "var(--success)", borderRadius: "6px", marginBottom: "16px" }}>
          {successMsg}
          <button onClick={() => setSuccessMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--success)" }}>✕</button>
        </div>
      )}

      {/* Action Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Enterprise User Registry</h3>
        <button
          type="button"
          onClick={() => {
            setShowCreateModal(true);
            if (orgs && orgs.length > 0) setNewUserOrgId(orgs[0].id);
          }}
          style={{
            background: "var(--primary)",
            border: "none",
            color: "#fff",
            padding: "8px 16px",
            borderRadius: "4px",
            fontSize: "13px",
            fontWeight: 600,
          }}
        >
          + Add User
        </button>
      </div>

      {/* Users Table */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
          <thead>
            <tr style={{ background: "var(--surface-raised)", borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>USER NAME & EMAIL</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>ROLE</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>ORGANIZATION</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>STATUS</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>CREATED</th>
              <th style={{ padding: "12px 16px", fontWeight: 650, textAlign: "right" }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {users && users.length > 0 ? (
              users.map((u) => {
                const isUserSuperAdmin = u.role === "superadmin";

                return (
                  <tr key={u.id} style={{ borderBottom: "1px solid var(--border)", opacity: u.is_active ? 1 : 0.6 }}>
                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{u.name}</div>
                      <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{u.email}</div>
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          padding: "3px 8px",
                          borderRadius: "4px",
                          background: isUserSuperAdmin ? "rgba(166,70,189,0.2)" : "var(--surface-raised)",
                          color: isUserSuperAdmin ? "var(--primary)" : "var(--text-primary)",
                          border: isUserSuperAdmin ? "1px solid rgba(166,70,189,0.4)" : "1px solid var(--border)",
                        }}
                      >
                        {u.role.toUpperCase()}
                      </span>
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                        {u.organization_name ? `${u.organization_name} (${u.organization_code})` : isUserSuperAdmin ? "Global (All Orgs)" : "Unassigned"}
                      </div>
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          padding: "3px 8px",
                          borderRadius: "12px",
                          background: u.is_active ? "var(--success-bg)" : "var(--danger-bg)",
                          color: u.is_active ? "var(--success)" : "var(--danger)",
                        }}
                      >
                        {u.is_active ? "Active" : "Deactivated"}
                      </span>
                    </td>

                    <td style={{ padding: "14px 16px", color: "var(--text-muted)", fontSize: "12px" }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "N/A"}
                    </td>

                    <td style={{ padding: "14px 16px", textAlign: "right" }}>
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingUser(u);
                            setEditRole(u.role);
                            setEditOrgId(u.organization_id || "");
                          }}
                          style={{
                            background: "var(--surface-raised)",
                            border: "1px solid var(--border-hover)",
                            color: "var(--text-primary)",
                            padding: "4px 10px",
                            borderRadius: "4px",
                            fontSize: "12px",
                          }}
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          onClick={() => toggleStatusMutation.mutate({ userId: u.id, isCurrentlyActive: u.is_active })}
                          disabled={toggleStatusMutation.isPending}
                          style={{
                            background: u.is_active ? "var(--danger-bg)" : "var(--success-bg)",
                            border: u.is_active ? "1px solid rgba(248,113,113,0.3)" : "1px solid rgba(70,189,146,0.3)",
                            color: u.is_active ? "var(--danger)" : "var(--success)",
                            padding: "4px 10px",
                            borderRadius: "4px",
                            fontSize: "12px",
                          }}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={6} style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>
                  No users found matching current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Create User */}
      {showCreateModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "440px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Create Enterprise User</h3>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Full Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Rahul Sharma"
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Email Address *</label>
                <input
                  type="email"
                  placeholder="e.g. rahul@jkcements.com"
                  value={newUserEmail}
                  onChange={(e) => setNewUserEmail(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Password *</label>
                <input
                  type="password"
                  placeholder="Enter initial password"
                  value={newUserPassword}
                  onChange={(e) => setNewUserPassword(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>User Role *</label>
                <select
                  value={newUserRole}
                  onChange={(e) => setNewUserRole(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="org_admin">Organization Administrator (org_admin)</option>
                  {isSuperAdmin && <option value="superadmin">Global Superadmin (superadmin)</option>}
                </select>
              </div>

              {isSuperAdmin && newUserRole !== "superadmin" && (
                <div>
                  <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Organization</label>
                  <select
                    value={newUserOrgId}
                    onChange={(e) => setNewUserOrgId(e.target.value)}
                    style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                  >
                    <option value="">-- Select Organization --</option>
                    {orgs?.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name} ({o.code})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button onClick={() => setShowCreateModal(false)} style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px" }}>
                Cancel
              </button>
              <button
                onClick={() => createUserMutation.mutate()}
                disabled={!newUserName || !newUserEmail || !newUserPassword || createUserMutation.isPending}
                style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600 }}
              >
                {createUserMutation.isPending ? "Creating..." : "Create User"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Edit User */}
      {editingUser && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "440px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Edit User Role & Scope</h3>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>User Name</label>
                <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>{editingUser.name} ({editingUser.email})</div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Role</label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="org_admin">Organization Administrator (org_admin)</option>
                  {isSuperAdmin && <option value="superadmin">Global Superadmin (superadmin)</option>}
                </select>
              </div>

              {isSuperAdmin && editRole !== "superadmin" && (
                <div>
                  <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Organization</label>
                  <select
                    value={editOrgId}
                    onChange={(e) => setEditOrgId(e.target.value)}
                    style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                  >
                    <option value="">-- Select Organization --</option>
                    {orgs?.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name} ({o.code})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button onClick={() => setEditingUser(null)} style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px" }}>
                Cancel
              </button>
              <button
                onClick={() => updateUserMutation.mutate(editingUser)}
                disabled={updateUserMutation.isPending}
                style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600 }}
              >
                {updateUserMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}