/**
 * HMAC-SHA256 request signing for admin proxy → FastAPI.
 *
 * Server-only module — uses Node.js crypto, never runs in browser.
 * Canonical string format: METHOD|normalizedPath|sortedQueryString|timestamp|userId|bodyHash
 *
 * @module
 */

import { createHmac, createHash } from "crypto";

// ---------------------------------------------------------------------------
// Path normalization (must match Python verifier exactly)
// ---------------------------------------------------------------------------

export function normalizePath(path: string): string {
  // Lowercase
  let normalized = path.toLowerCase();
  // Collapse consecutive slashes
  normalized = normalized.replace(/\/+/g, "/");
  // Strip trailing slash (but keep root /)
  if (normalized.length > 1 && normalized.endsWith("/")) {
    normalized = normalized.slice(0, -1);
  }
  // Reject path traversal
  const segments = normalized.split("/");
  if (segments.some((s) => s === "..")) {
    throw new Error("Path traversal detected: '..' segments not allowed");
  }
  return normalized;
}

// ---------------------------------------------------------------------------
// Query string sorting
// ---------------------------------------------------------------------------

export function sortQueryString(queryString: string): string {
  if (!queryString) return "";
  const params = queryString.split("&").filter(Boolean);
  params.sort();
  return params.join("&");
}

// ---------------------------------------------------------------------------
// Body hash
// ---------------------------------------------------------------------------

export function computeBodyHash(body: string | Buffer): string {
  const data = typeof body === "string" ? Buffer.from(body, "utf-8") : body;
  return createHash("sha256").update(data).digest("hex");
}

// ---------------------------------------------------------------------------
// Canonical string + HMAC signature
// ---------------------------------------------------------------------------

export function computeCanonicalString(
  method: string,
  normalizedPath: string,
  sortedQueryString: string,
  timestamp: number,
  userId: string,
  bodyHash: string
): string {
  return `${method}|${normalizedPath}|${sortedQueryString}|${timestamp}|${userId}|${bodyHash}`;
}

export function computeSignature(
  canonicalString: string,
  secret: string
): string {
  return createHmac("sha256", secret).update(canonicalString, "utf-8").digest("hex");
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface SignedHeaders {
  "X-Admin-Signature": string;
  "X-Admin-Timestamp": string;
  "X-Admin-User-Id": string;
  "X-Admin-Body-Hash": string;
}

/**
 * Sign an admin request for the HMAC proxy.
 *
 * @param method - HTTP method (GET, POST, PATCH, DELETE)
 * @param path - Request path (will be normalized)
 * @param queryString - Raw query string (will be sorted)
 * @param userId - Verified admin user ID from JWT session
 * @param body - Request body (empty string for GET)
 * @returns Headers to attach to the outbound request
 * @throws If ADMIN_HMAC_SECRET is not configured
 */
export function signAdminRequest(
  method: string,
  path: string,
  queryString: string,
  userId: string,
  body: string | Buffer = ""
): SignedHeaders {
  const secret = process.env.ADMIN_HMAC_SECRET;
  if (!secret) {
    throw new Error(
      "ADMIN_HMAC_SECRET is not configured. Admin proxy cannot sign requests."
    );
  }

  const normalizedPath = normalizePath(path);
  const sortedQS = sortQueryString(queryString);
  const bodyHash = computeBodyHash(body);
  const timestamp = Math.floor(Date.now() / 1000);

  const canonical = computeCanonicalString(
    method,
    normalizedPath,
    sortedQS,
    timestamp,
    userId,
    bodyHash
  );
  const signature = computeSignature(canonical, secret);

  return {
    "X-Admin-Signature": signature,
    "X-Admin-Timestamp": String(timestamp),
    "X-Admin-User-Id": userId,
    "X-Admin-Body-Hash": bodyHash,
  };
}
