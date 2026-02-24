/**
 * POST /api/upload/signed-url
 *
 * Issues a GCS signed PUT URL so the client can upload a trip photo directly
 * to Cloud Storage without routing the binary through this server.
 *
 * Security controls (per review-posttrip.md SEC-1):
 * - Content-Type condition on the signed URL — GCS rejects mismatched uploads.
 * - x-goog-content-length-range: 0,10485760 — GCS enforces max 10 MB server-side.
 *   Client-declared file size cannot be trusted; this condition is the real gate.
 * - Object path is fully server-generated (tripId validated, slotId validated,
 *   UUID prefix, sanitized filename). No user input reaches the path directly.
 * - Photos are served from the GCS domain, not the app domain, preventing XSS
 *   via an uploaded HTML file declared as image/jpeg.
 *
 * Dev fallback:
 * If GCS_BUCKET or GOOGLE_APPLICATION_CREDENTIALS is not configured, the handler
 * returns a mock response with a local path. This allows PhotoStrip to work in
 * development without a GCS project. The mock uploadUrl is a no-op placeholder —
 * the client PUT will fail with a network error, but the component state machine
 * can be tested by mocking fetch at the component level. See TEST-2 in
 * docs/mvp/review-posttrip.md for the recommended test strategy.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";
import { Storage } from "@google-cloud/storage";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

// ---------- Constants ----------

const ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
type AllowedContentType = (typeof ALLOWED_CONTENT_TYPES)[number];

/** 15 minutes in seconds */
const SIGNED_URL_EXPIRES_IN_SECONDS = 900;

/** 10 MB in bytes — must match x-goog-content-length-range max */
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

// ---------- Validation schema ----------

const signedUrlSchema = z.object({
  tripId: z.string().uuid(),
  slotId: z.string().uuid(),
  /**
   * filename is optional — the PhotoStrip client does not send it, but callers
   * that do send a filename will have it sanitized and appended to the object path
   * for readability. When absent, the object path is UUID-only.
   */
  filename: z.string().max(255).optional(),
  contentType: z.enum(ALLOWED_CONTENT_TYPES),
  /**
   * fileSizeBytes is declared by the client and used only for an early 400
   * response. It is NOT the actual enforcement gate — that is handled by
   * x-goog-content-length-range on the signed URL itself.
   */
  fileSizeBytes: z.number().int().positive().max(MAX_FILE_SIZE_BYTES).optional(),
});

type SignedUrlInput = z.infer<typeof signedUrlSchema>;

// ---------- Helpers ----------

/**
 * Strip directory components and control characters from a filename.
 * Collapse runs of unsafe characters to underscores.
 * Limit to 100 characters.
 */
function sanitizeFilename(raw: string): string {
  // Strip path components (Windows and Unix separators)
  const basename = raw.replace(/^.*[\\/]/, "");
  // Replace any character that is not alphanumeric, dot, hyphen, or underscore
  const safe = basename.replace(/[^a-zA-Z0-9.\-_]/g, "_");
  // Collapse consecutive underscores, trim leading/trailing underscores
  return safe.replace(/_+/g, "_").replace(/^_|_$/g, "").slice(0, 100);
}

/**
 * Build the GCS object path.
 * Format: photos/{tripId}/{slotId}/{uuid}-{sanitizedFilename}
 *         photos/{tripId}/{slotId}/{uuid}   (when filename is absent)
 */
function buildObjectPath(
  tripId: string,
  slotId: string,
  filename: string | undefined
): string {
  const id = uuidv4();
  if (filename) {
    const safe = sanitizeFilename(filename);
    // Guard against filenames that sanitize down to nothing
    const suffix = safe.length > 0 ? `-${safe}` : "";
    return `photos/${tripId}/${slotId}/${id}${suffix}`;
  }
  return `photos/${tripId}/${slotId}/${id}`;
}

/**
 * Detect whether GCS is configured in this environment.
 * Returns false in local dev when GCS_BUCKET or credentials are absent.
 */
function isGcsConfigured(): boolean {
  return Boolean(
    process.env.GCS_BUCKET &&
      (process.env.GOOGLE_APPLICATION_CREDENTIALS ||
        // Cloud Run / GKE workload identity injects metadata server credentials
        // without an explicit credential file — treat non-local envs as configured.
        process.env.NODE_ENV === "production")
  );
}

// ---------- Route handler ----------

export async function POST(req: NextRequest) {
  // --- 1. Auth ---
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // --- 2. Parse + validate body ---
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = signedUrlSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "Validation failed",
        details: parsed.error.flatten().fieldErrors,
      },
      { status: 400 }
    );
  }

  const { tripId, slotId, filename, contentType, fileSizeBytes }: SignedUrlInput =
    parsed.data;

  // Early rejection if the client self-reports a file that exceeds the limit.
  // The real server-side enforcement is x-goog-content-length-range on the URL.
  if (fileSizeBytes !== undefined && fileSizeBytes > MAX_FILE_SIZE_BYTES) {
    return NextResponse.json(
      { error: "File size exceeds the 10 MB limit" },
      { status: 400 }
    );
  }

  // --- 3. Authorization: caller must be a joined TripMember ---
  try {
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // --- 4. Validate that slotId belongs to the trip ---
    const slot = await prisma.itinerarySlot.findUnique({
      where: { id: slotId },
      select: { tripId: true },
    });

    if (!slot || slot.tripId !== tripId) {
      return NextResponse.json(
        { error: "Slot not found or does not belong to this trip" },
        { status: 404 }
      );
    }
  } catch (err) {
    console.error("[POST /api/upload/signed-url] DB error during auth check:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  // --- 5. Dev fallback: return a mock response when GCS is not configured ---
  // DEV ONLY — this block must never run in production.
  // It exists solely so PhotoStrip renders and the upload state machine is
  // exercisable locally without a GCS project. The uploadUrl is a no-op URL;
  // the actual PUT to GCS will not succeed. Mock the fetch calls in tests instead
  // (see TEST-2 in docs/mvp/review-posttrip.md).
  if (!isGcsConfigured()) {
    const objectPath = buildObjectPath(tripId, slotId, filename);
    const mockPublicUrl = `/dev-uploads/${objectPath}`;
    console.warn(
      "[POST /api/upload/signed-url] GCS not configured — returning mock response. " +
        "Set GCS_BUCKET and GOOGLE_APPLICATION_CREDENTIALS for real uploads."
    );
    return NextResponse.json(
      {
        data: {
          uploadUrl: `http://localhost:3000/api/dev-upload-placeholder?path=${encodeURIComponent(objectPath)}`,
          publicUrl: mockPublicUrl,
          objectPath,
          expiresInSeconds: SIGNED_URL_EXPIRES_IN_SECONDS,
        },
      },
      { status: 200 }
    );
  }

  // --- 6. Generate GCS signed URL ---
  const bucketName = process.env.GCS_BUCKET ?? "overplanned-uploads";
  const objectPath = buildObjectPath(tripId, slotId, filename);
  const expiresAt = Date.now() + SIGNED_URL_EXPIRES_IN_SECONDS * 1_000;

  try {
    const storage = new Storage();
    const bucket = storage.bucket(bucketName);
    const file = bucket.file(objectPath);

    const [uploadUrl] = await file.getSignedUrl({
      version: "v4",
      action: "write",
      expires: expiresAt,
      contentType: contentType as AllowedContentType,
      extensionHeaders: {
        // Server-side file size enforcement (SEC-1 from review-posttrip.md).
        // GCS rejects any PUT whose Content-Length falls outside this range.
        // This is the authoritative gate — client-declared fileSizeBytes is advisory.
        "x-goog-content-length-range": `0,${MAX_FILE_SIZE_BYTES}`,
      },
    });

    // Construct the public read URL.
    // Objects in this bucket are expected to be publicly readable via the GCS
    // storage.googleapis.com domain, which prevents XSS by isolating user-uploaded
    // content from the app domain (app.overplanned.co).
    const publicUrl = `https://storage.googleapis.com/${bucketName}/${objectPath}`;

    return NextResponse.json(
      {
        data: {
          uploadUrl,
          publicUrl,
          objectPath,
          expiresInSeconds: SIGNED_URL_EXPIRES_IN_SECONDS,
        },
      },
      { status: 200 }
    );
  } catch (err) {
    console.error("[POST /api/upload/signed-url] GCS signed URL error:", err);
    return NextResponse.json(
      { error: "Failed to generate upload URL" },
      { status: 500 }
    );
  }
}
