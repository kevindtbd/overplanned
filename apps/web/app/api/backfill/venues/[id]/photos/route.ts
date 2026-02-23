/**
 * POST /api/backfill/venues/[id]/photos  — Upload a photo to a backfill venue
 * GET  /api/backfill/venues/[id]/photos  — List photos for a venue (signed URLs)
 *
 * Upload constraints:
 *   - Max file size: 10 MB
 *   - Allowed MIME types: image/jpeg, image/png, image/webp, image/heic
 *     (validated from magic bytes — NOT from Content-Type or filename)
 *   - Max 20 photos per venue
 *
 * GCS path: backfill-photos/{userId}/{venueId}/{uuid}.{ext}
 * Filename: UUID derived — user-provided filename is NEVER used in the path.
 *
 * EXIF: GPS coordinates clamped and rounded to 3dp; timestamp extracted.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { BackfillAuthError, verifyBackfillVenueOwnership } from "@/lib/backfill-auth";
import { uploadToGCS, getSignedUrl } from "@/lib/gcs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const MAX_PHOTOS_PER_VENUE = 20;

// ---------------------------------------------------------------------------
// Magic byte detection
// ---------------------------------------------------------------------------

function detectMime(buffer: Buffer): { mime: string; ext: string } | null {
  // JPEG
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    return { mime: "image/jpeg", ext: "jpg" };
  }

  // PNG
  if (
    buffer[0] === 0x89 &&
    buffer[1] === 0x50 &&
    buffer[2] === 0x4e &&
    buffer[3] === 0x47 &&
    buffer[4] === 0x0d &&
    buffer[5] === 0x0a &&
    buffer[6] === 0x1a &&
    buffer[7] === 0x0a
  ) {
    return { mime: "image/png", ext: "png" };
  }

  // WebP: RIFF at 0..3, WEBP at 8..11 — needs at least 12 bytes
  if (
    buffer.length >= 12 &&
    buffer[0] === 0x52 &&
    buffer[1] === 0x49 &&
    buffer[2] === 0x46 &&
    buffer[3] === 0x46 &&
    buffer[8] === 0x57 &&
    buffer[9] === 0x45 &&
    buffer[10] === 0x42 &&
    buffer[11] === 0x50
  ) {
    return { mime: "image/webp", ext: "webp" };
  }

  // HEIC / HEIF: ISO BMFF — "ftyp" box at offset 4, brand starting at 8
  // Brands: heic, heix, hevc, hevx, mif1, msf1
  if (buffer.length >= 12) {
    const ftyp =
      buffer[4] === 0x66 && // f
      buffer[5] === 0x74 && // t
      buffer[6] === 0x79 && // y
      buffer[7] === 0x70;   // p
    if (ftyp) {
      const brand = buffer.slice(8, 12).toString("ascii");
      const heicBrands = ["heic", "heix", "hevc", "hevx", "mif1", "msf1"];
      if (heicBrands.includes(brand)) {
        return { mime: "image/heic", ext: "heic" };
      }
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// EXIF extraction via sharp
// ---------------------------------------------------------------------------

interface ExifResult {
  lat: number | null;
  lng: number | null;
  timestamp: Date | null;
}

async function extractExif(buffer: Buffer): Promise<ExifResult> {
  try {
    // exifr handles its own empty-EXIF case and returns null when no GPS data
    // is present. Dynamic import keeps it out of the main bundle.
    const exifr = await import("exifr").catch(() => null);
    if (!exifr) return { lat: null, lng: null, timestamp: null };

    const parsed = await exifr.default.parse(buffer, {
      gps: true,
      pick: ["latitude", "longitude", "DateTimeOriginal", "GPSDateStamp", "GPSTimeStamp"],
    }).catch(() => null);

    if (!parsed) return { lat: null, lng: null, timestamp: null };

    let lat: number | null = null;
    let lng: number | null = null;
    let timestamp: Date | null = null;

    if (
      typeof parsed.latitude === "number" &&
      typeof parsed.longitude === "number" &&
      isFinite(parsed.latitude) &&
      isFinite(parsed.longitude)
    ) {
      // Clamp to valid ranges, round to 3 decimal places (~110m precision)
      const rawLat = Math.max(-90, Math.min(90, parsed.latitude));
      const rawLng = Math.max(-180, Math.min(180, parsed.longitude));
      lat = Math.round(rawLat * 1000) / 1000;
      lng = Math.round(rawLng * 1000) / 1000;
    }

    if (parsed.DateTimeOriginal instanceof Date && !isNaN(parsed.DateTimeOriginal.getTime())) {
      timestamp = parsed.DateTimeOriginal;
    }

    return { lat, lng, timestamp };
  } catch {
    // EXIF extraction is best-effort — never block the upload
    return { lat: null, lng: null, timestamp: null };
  }
}

// ---------------------------------------------------------------------------
// POST — upload
// ---------------------------------------------------------------------------

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: venueId } = params;

  try {
    // Ownership check
    await verifyBackfillVenueOwnership(venueId, userId);

    // Parse multipart form data
    let formData: FormData;
    try {
      formData = await req.formData();
    } catch {
      return NextResponse.json({ error: "Invalid multipart form data" }, { status: 400 });
    }

    const file = formData.get("file");
    if (!file || !(file instanceof Blob)) {
      return NextResponse.json({ error: "Missing file field" }, { status: 400 });
    }

    // Size check
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return NextResponse.json(
        { error: "File too large", detail: "Maximum file size is 10 MB" },
        { status: 400 }
      );
    }

    const buffer = Buffer.from(await file.arrayBuffer());

    // MIME detection from magic bytes — do NOT trust file.type or filename
    const detected = detectMime(buffer);
    if (!detected) {
      return NextResponse.json(
        {
          error: "Unsupported file type",
          detail: "Allowed types: JPEG, PNG, WebP, HEIC",
        },
        { status: 415 }
      );
    }

    // Max photos per venue guard
    const existingCount = await prisma.backfillPhoto.count({
      where: { backfillVenueId: venueId },
    });

    if (existingCount >= MAX_PHOTOS_PER_VENUE) {
      return NextResponse.json(
        {
          error: "Photo limit reached",
          detail: `Maximum ${MAX_PHOTOS_PER_VENUE} photos per venue`,
        },
        { status: 409 }
      );
    }

    // Extract EXIF (best-effort)
    const exif = await extractExif(buffer);

    // Build GCS path — UUID filename, extension from validated MIME
    const fileId = uuidv4();
    const gcsPath = `backfill-photos/${userId}/${venueId}/${fileId}.${detected.ext}`;

    // Upload to GCS
    await uploadToGCS(buffer, gcsPath, detected.mime);

    // Persist DB row
    const photo = await prisma.backfillPhoto.create({
      data: {
        backfillVenueId: venueId,
        gcsPath,
        originalFilename: (file as File).name ?? "upload",
        mimeType: detected.mime,
        exifLat: exif.lat,
        exifLng: exif.lng,
        exifTimestamp: exif.timestamp,
      },
      select: {
        id: true,
        gcsPath: true,
        exifLat: true,
        exifLng: true,
        exifTimestamp: true,
        createdAt: true,
      },
    });

    // Generate signed URL for immediate display
    let signedUrl: string | null = null;
    try {
      signedUrl = await getSignedUrl(gcsPath);
    } catch (err) {
      console.error(`[POST /api/backfill/venues/${venueId}/photos] Sign URL error:`, err);
    }

    return NextResponse.json(
      {
        id: photo.id,
        signedUrl,
        exifLat: photo.exifLat,
        exifLng: photo.exifLng,
        exifTimestamp: photo.exifTimestamp,
      },
      { status: 201 }
    );
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[POST /api/backfill/venues/${venueId}/photos] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

// ---------------------------------------------------------------------------
// GET — list photos
// ---------------------------------------------------------------------------

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: venueId } = params;

  try {
    await verifyBackfillVenueOwnership(venueId, userId);

    const photos = await prisma.backfillPhoto.findMany({
      where: { backfillVenueId: venueId },
      select: {
        id: true,
        gcsPath: true,
        exifLat: true,
        exifLng: true,
        exifTimestamp: true,
        createdAt: true,
      },
      orderBy: { createdAt: "asc" },
    });

    const photosWithUrls = await Promise.all(
      photos.map(async (photo) => {
        let signedUrl: string | null = null;
        try {
          signedUrl = await getSignedUrl(photo.gcsPath);
        } catch (err) {
          console.error(
            `[GET /api/backfill/venues/${venueId}/photos] Sign URL error for ${photo.id}:`,
            err
          );
        }
        return {
          id: photo.id,
          signedUrl,
          exifLat: photo.exifLat,
          exifLng: photo.exifLng,
          exifTimestamp: photo.exifTimestamp,
          createdAt: photo.createdAt,
        };
      })
    );

    return NextResponse.json({ photos: photosWithUrls }, { status: 200 });
  } catch (err) {
    if (err instanceof BackfillAuthError) return err.toResponse();
    console.error(`[GET /api/backfill/venues/${venueId}/photos] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
