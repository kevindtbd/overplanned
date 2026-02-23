/**
 * GCS helper — upload, delete, and sign URLs for backfill photo storage.
 *
 * Bucket: GCS_BACKFILL_BUCKET env var (required at runtime).
 * Auth: Application Default Credentials (ADC) via GOOGLE_APPLICATION_CREDENTIALS
 * or the attached Cloud Run service account in production.
 */

import { Storage } from "@google-cloud/storage";

const storage = new Storage();

function getBucket() {
  const bucket = process.env.GCS_BACKFILL_BUCKET;
  if (!bucket) {
    throw new Error("GCS_BACKFILL_BUCKET environment variable is not set");
  }
  return storage.bucket(bucket);
}

/**
 * Upload a buffer to GCS at the given path with the given content type.
 * Overwrites any existing object at that path.
 */
export async function uploadToGCS(
  buffer: Buffer,
  path: string,
  contentType: string
): Promise<void> {
  const bucket = getBucket();
  const file = bucket.file(path);
  await file.save(buffer, {
    contentType,
    resumable: false,
    metadata: {
      cacheControl: "private, no-store",
    },
  });
}

/**
 * Delete an object from GCS. Silently succeeds if the object does not exist.
 */
export async function deleteFromGCS(path: string): Promise<void> {
  const bucket = getBucket();
  const file = bucket.file(path);
  try {
    await file.delete();
  } catch (err: unknown) {
    // GCS returns 404 as an error — treat it as a no-op
    if (
      typeof err === "object" &&
      err !== null &&
      "code" in err &&
      (err as { code: unknown }).code === 404
    ) {
      return;
    }
    throw err;
  }
}

/**
 * Generate a signed URL for a GCS object.
 * Default expiry: 15 minutes.
 * Response disposition set to "attachment" to prevent inline rendering.
 */
export async function getSignedUrl(
  path: string,
  expiresInMinutes = 15
): Promise<string> {
  const bucket = getBucket();
  const file = bucket.file(path);

  const [url] = await file.getSignedUrl({
    version: "v4",
    action: "read",
    expires: Date.now() + expiresInMinutes * 60 * 1_000,
    responseDisposition: "attachment",
  });

  return url;
}
