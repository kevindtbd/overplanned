import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  normalizePath,
  sortQueryString,
  computeBodyHash,
  computeCanonicalString,
  computeSignature,
  signAdminRequest,
} from "@/lib/admin/sign-request";

import testVectors from "../../../../test-vectors/admin-hmac-vectors.json";

const TEST_SECRET =
  "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2";

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("ADMIN_HMAC_SECRET", TEST_SECRET);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

// ---------------------------------------------------------------------------
// Shared test vectors
// ---------------------------------------------------------------------------

describe("sign-request: shared test vectors", () => {
  const signingVectors = testVectors.vectors.filter(
    (v) => "expectedSignature" in v && "method" in v && !("method_a" in v)
  );

  it.each(signingVectors.map((v) => [v.description, v]))(
    "matches vector: %s",
    (_desc, vector) => {
      const v = vector as {
        description: string; method: string; path: string;
        queryString: string; body: string; timestamp: number;
        userId: string; secret: string; expectedSignature: string;
        expectedBodyHash: string;
      };
      const normalizedPath = normalizePath(v.path);
      const sortedQS = sortQueryString(v.queryString);
      const bodyHash = computeBodyHash(v.body);

      expect(bodyHash).toBe(v.expectedBodyHash);

      const canonical = computeCanonicalString(
        v.method,
        normalizedPath,
        sortedQS,
        v.timestamp,
        v.userId,
        bodyHash
      );
      const signature = computeSignature(canonical, v.secret);

      expect(signature).toBe(v.expectedSignature);
    }
  );

  it("produces different signatures for different HTTP methods (GET vs POST)", () => {
    const diffVector = testVectors.vectors.find(
      (v) => "method_a" in v
    ) as (typeof testVectors.vectors)[number] & {
      method_a: string;
      method_b: string;
      signature_a: string;
      signature_b: string;
    };

    const normalizedPath = normalizePath(diffVector.path);
    const sortedQS = sortQueryString(diffVector.queryString);
    const bodyHash = computeBodyHash(diffVector.body);

    const canonicalA = computeCanonicalString(
      diffVector.method_a,
      normalizedPath,
      sortedQS,
      diffVector.timestamp,
      diffVector.userId,
      bodyHash
    );
    const canonicalB = computeCanonicalString(
      diffVector.method_b,
      normalizedPath,
      sortedQS,
      diffVector.timestamp,
      diffVector.userId,
      bodyHash
    );

    const sigA = computeSignature(canonicalA, diffVector.secret);
    const sigB = computeSignature(canonicalB, diffVector.secret);

    expect(sigA).toBe(diffVector.signature_a);
    expect(sigB).toBe(diffVector.signature_b);
    expect(sigA).not.toBe(sigB);
  });
});

// ---------------------------------------------------------------------------
// Body hash
// ---------------------------------------------------------------------------

describe("computeBodyHash", () => {
  it("returns SHA-256 of empty string for GET (no body)", () => {
    const hash = computeBodyHash("");
    expect(hash).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
  });

  it("hashes JSON body correctly (POST)", () => {
    const hash = computeBodyHash('{"target_stage":"ab_test"}');
    expect(hash).toBe(
      "92960f2aa105f68c3557610b09d89e58c4b60d991c0c60f39c9697e951b85ba8"
    );
  });

  it("hashes empty body as empty-string SHA-256 (POST with empty body)", () => {
    expect(computeBodyHash("")).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
  });

  it("handles Unicode body correctly", () => {
    const hash = computeBodyHash('{"name":"Caf\u00e9 de Flore"}');
    expect(hash).toBe(
      "92984a3870bf810c856751afe04a63593ffd5a71bf2b509407f1a523341a07d6"
    );
  });

  it("accepts Buffer input", () => {
    const buf = Buffer.from('{"key":"value"}', "utf-8");
    const hashFromBuf = computeBodyHash(buf);
    const hashFromStr = computeBodyHash('{"key":"value"}');
    expect(hashFromBuf).toBe(hashFromStr);
  });
});

// ---------------------------------------------------------------------------
// Canonical string format
// ---------------------------------------------------------------------------

describe("computeCanonicalString", () => {
  it("joins fields with pipe delimiter in correct order", () => {
    const result = computeCanonicalString(
      "GET",
      "/admin/users",
      "",
      1700000000,
      "user-001",
      "abc123"
    );
    expect(result).toBe("GET|/admin/users||1700000000|user-001|abc123");
  });

  it("includes sorted query string in the third field", () => {
    const result = computeCanonicalString(
      "GET",
      "/admin/nodes",
      "city=tokyo&search=ramen&sort=name",
      1700000800,
      "user-001",
      "def456"
    );
    expect(result).toBe(
      "GET|/admin/nodes|city=tokyo&search=ramen&sort=name|1700000800|user-001|def456"
    );
  });
});

// ---------------------------------------------------------------------------
// Path normalization
// ---------------------------------------------------------------------------

describe("normalizePath", () => {
  it("removes trailing slash", () => {
    expect(normalizePath("/admin/users/")).toBe("/admin/users");
  });

  it("keeps root slash as-is", () => {
    expect(normalizePath("/")).toBe("/");
  });

  it("collapses double slashes", () => {
    expect(normalizePath("/admin//models")).toBe("/admin/models");
  });

  it("collapses triple slashes", () => {
    expect(normalizePath("/admin///models///list")).toBe("/admin/models/list");
  });

  it("throws on '..' path traversal", () => {
    expect(() => normalizePath("/admin/../etc/passwd")).toThrow(
      "Path traversal detected"
    );
  });

  it("lowercases the path", () => {
    expect(normalizePath("/Admin/Users")).toBe("/admin/users");
  });
});

// ---------------------------------------------------------------------------
// Query string sorting
// ---------------------------------------------------------------------------

describe("sortQueryString", () => {
  it("sorts unsorted params lexicographically", () => {
    expect(sortQueryString("sort=name&city=tokyo&search=ramen")).toBe(
      "city=tokyo&search=ramen&sort=name"
    );
  });

  it("returns empty string for empty input", () => {
    expect(sortQueryString("")).toBe("");
  });

  it("returns single param unchanged", () => {
    expect(sortQueryString("key=value")).toBe("key=value");
  });

  it("handles already-sorted params", () => {
    expect(sortQueryString("a=1&b=2&c=3")).toBe("a=1&b=2&c=3");
  });
});

// ---------------------------------------------------------------------------
// signAdminRequest (public API)
// ---------------------------------------------------------------------------

describe("signAdminRequest", () => {
  it("throws when ADMIN_HMAC_SECRET is not set", () => {
    vi.stubEnv("ADMIN_HMAC_SECRET", "");
    expect(() =>
      signAdminRequest("GET", "/admin/users", "", "user-001")
    ).toThrow("ADMIN_HMAC_SECRET is not configured");
  });

  it("returns all four signed headers", () => {
    const headers = signAdminRequest("GET", "/admin/users", "", "user-001");
    expect(headers).toHaveProperty("X-Admin-Signature");
    expect(headers).toHaveProperty("X-Admin-Timestamp");
    expect(headers).toHaveProperty("X-Admin-User-Id");
    expect(headers).toHaveProperty("X-Admin-Body-Hash");
  });

  it("sets X-Admin-User-Id to the provided userId", () => {
    const headers = signAdminRequest(
      "GET",
      "/admin/users",
      "",
      "my-admin-id"
    );
    expect(headers["X-Admin-User-Id"]).toBe("my-admin-id");
  });

  it("is deterministic: same inputs produce same output", () => {
    // Fix Date.now so timestamp is stable
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1700000000000);
    const a = signAdminRequest("GET", "/admin/users", "", "user-001");
    const b = signAdminRequest("GET", "/admin/users", "", "user-001");
    expect(a).toEqual(b);
    nowSpy.mockRestore();
  });

  it("produces different signatures for different methods (GET vs POST)", () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1700000000000);
    const getHeaders = signAdminRequest(
      "GET",
      "/admin/users",
      "",
      "user-001"
    );
    const postHeaders = signAdminRequest(
      "POST",
      "/admin/users",
      "",
      "user-001",
      ""
    );
    expect(getHeaders["X-Admin-Signature"]).not.toBe(
      postHeaders["X-Admin-Signature"]
    );
    nowSpy.mockRestore();
  });
});
