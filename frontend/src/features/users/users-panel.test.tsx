import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { UsersPanel } from "./users-panel"

const users = [
  { username: "admin", role: "admin" as const, auth_source: "local" as const, created_at: "2026-09-01T10:00:00Z", last_seen_at: "2026-09-03T08:00:00Z" },
  { username: "anna", role: "viewer" as const, auth_source: "sso" as const, created_at: "2026-09-02T10:00:00Z", last_seen_at: null },
]

it("loads, searches, and updates user roles for an administrator", async () => {
  const user = userEvent.setup()
  const fetchJson = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") return { ...users[1], role: "admin" }
    expect(url).toBe("/api/users")
    return { users }
  })
  render(<UsersPanel active language="ru" currentUsername="admin" currentRole="admin" fetchJson={fetchJson as never} />)

  expect(await screen.findByText("anna")).toBeInTheDocument()
  expect(screen.getByLabelText("Пользователи: 2")).toBeInTheDocument()
  expect(screen.getByText("В системе должен остаться хотя бы один администратор.")).toBeInTheDocument()
  expect(screen.getAllByText("A", { selector: "[data-initials]" })).toHaveLength(2)
  await user.type(screen.getByRole("textbox", { name: "Поиск пользователя" }), "anna")
  expect(within(screen.getByRole("table")).queryByText("admin")).not.toBeInTheDocument()

  await user.click(screen.getByRole("combobox", { name: "Роль: anna" }))
  await user.click(screen.getByRole("option", { name: "Администратор" }))
  await waitFor(() => expect(fetchJson).toHaveBeenCalledWith("/api/users/anna/role", expect.objectContaining({ method: "PATCH" })))
})

it("keeps role controls disabled for a viewer", async () => {
  const fetchJson = vi.fn(async () => ({ users }))
  render(<UsersPanel active language="en" currentUsername="anna" currentRole="viewer" fetchJson={fetchJson as never} />)

  expect(await screen.findByText("Only administrators can change roles.")).toBeInTheDocument()
  for (const control of screen.getAllByRole("combobox")) expect(control).toBeDisabled()
})

it("updates the active workspace immediately after a safe self-demotion", async () => {
  const user = userEvent.setup()
  const onCurrentRoleChange = vi.fn()
  const admins = [users[0], { ...users[1], role: "admin" as const }]
  const fetchJson = vi.fn(async (_url: string, init?: RequestInit) => init?.method === "PATCH"
    ? { ...admins[0], role: "viewer" as const }
    : { users: admins })
  render(<UsersPanel active language="en" currentUsername="admin" currentRole="admin" fetchJson={fetchJson as never} onCurrentRoleChange={onCurrentRoleChange} />)

  await user.click(await screen.findByRole("combobox", { name: "Role: admin" }))
  await user.click(screen.getByRole("option", { name: "Viewer" }))

  await waitFor(() => expect(onCurrentRoleChange).toHaveBeenCalledWith("viewer"))
})
