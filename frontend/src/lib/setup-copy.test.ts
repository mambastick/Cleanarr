import { SETUP_CONNECTION_COPY } from "@/lib/setup-copy"

describe("first-run downloader copy", () => {
  it("contains complete ready and incomplete states in English and Russian", () => {
    for (const copy of [SETUP_CONNECTION_COPY.en, SETUP_CONNECTION_COPY.ru]) {
      expect(copy.connectionVerified).not.toHaveLength(0)
      expect(copy.connectionIncomplete).not.toHaveLength(0)
      expect(copy.enabledTopology).not.toHaveLength(0)
    }
  })
})
