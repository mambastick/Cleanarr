import { expect, it } from "vitest"
import { batchTransitionAnnouncement, isTerminalBatchStatus } from "./batch-status"

const batch = (status: "completed" | "partial" | "failed" | "cancelled") => ({ id: "batch", status, message: "PRIVATE", created_at: "", started_at: null, completed_at: null, error_code: "private", error_message: "PRIVATE", total_count: 0, queued_count: 0, running_count: 0, completed_count: 0, blocked_count: 0, failed_count: 0, cancelled_count: 0, children: [] })

it("announces only structured terminal batch states without backend text", () => { expect(isTerminalBatchStatus("running")).toBe(false); expect(isTerminalBatchStatus("partial")).toBe(true); const announcement = batchTransitionAnnouncement(batch("partial"), "en"); expect(announcement).toEqual({ message: "Batch job completed partially and needs attention.", tone: "assertive" }); expect(announcement.message).not.toContain("PRIVATE") })
