"use client";

// PhotoStrip — Per-slot photo upload strip for post-trip reflection.
// Uploads directly to GCS via server-generated signed URLs.
// Constraints: max 10MB, image/jpeg + image/png + image/webp only.

import { useState, useCallback, useRef } from "react";

// ---------- Types ----------

export interface PhotoStripSlot {
  slotId: string;
  activityName: string;
  imageUrl?: string;
}

export interface UploadedPhoto {
  slotId: string;
  publicUrl: string;
  objectPath: string;
}

interface PhotoStripProps {
  tripId: string;
  slots: PhotoStripSlot[];
  onUpload?: (photo: UploadedPhoto) => void;
}

type UploadState = "idle" | "uploading" | "done" | "error";

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

// ---------- Helpers ----------

async function getSignedUrl(tripId: string, slotId: string, file: File) {
  const res = await fetch("/api/upload/signed-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tripId,
      slotId,
      contentType: file.type,
      fileSizeBytes: file.size,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Failed to get upload URL (${res.status})`);
  }

  const json = await res.json();
  return json.data as { uploadUrl: string; publicUrl: string; objectPath: string };
}

async function uploadToGcs(uploadUrl: string, file: File) {
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });

  if (!res.ok) {
    throw new Error(`Upload failed (${res.status})`);
  }
}

// ---------- Single slot upload card ----------

function SlotUploadCard({
  slot,
  tripId,
  onUpload,
}: {
  slot: PhotoStripSlot;
  tripId: string;
  onUpload?: (photo: UploadedPhoto) => void;
}) {
  const [state, setState] = useState<UploadState>("idle");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      // Validate type
      if (!ALLOWED_TYPES.has(file.type)) {
        setError("Only JPEG, PNG, or WebP images allowed");
        return;
      }

      // Validate size
      if (file.size > MAX_FILE_SIZE) {
        setError("File must be under 10MB");
        return;
      }

      setError(null);
      setState("uploading");

      // Show local preview immediately
      const objectUrl = URL.createObjectURL(file);
      setPreview(objectUrl);

      try {
        const { uploadUrl, publicUrl, objectPath } = await getSignedUrl(
          tripId,
          slot.slotId,
          file
        );

        await uploadToGcs(uploadUrl, file);

        setState("done");
        onUpload?.({ slotId: slot.slotId, publicUrl, objectPath });
      } catch (err) {
        setState("error");
        setError(err instanceof Error ? err.message : "Upload failed");
        setPreview(null);
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    },
    [tripId, slot.slotId, onUpload]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const displayImage = preview || slot.imageUrl;

  return (
    <div
      className="shrink-0 w-36 space-y-2"
      role="group"
      aria-label={`Upload photo for ${slot.activityName}`}
    >
      {/* Upload target */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        disabled={state === "uploading"}
        className={`
          relative w-36 h-36 rounded-xl overflow-hidden
          border-2 border-dashed transition-all duration-150
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2
          disabled:cursor-wait
          ${
            state === "done"
              ? "border-emerald-400 bg-success-bg"
              : state === "error"
                ? "border-red-400 bg-error-bg"
                : "border-ink-700 bg-base hover:border-accent-muted hover:bg-surface"
          }
        `}
        aria-label={
          state === "done"
            ? `Photo uploaded for ${slot.activityName}`
            : `Upload photo for ${slot.activityName}`
        }
      >
        {displayImage ? (
          <img
            src={displayImage}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 p-2">
            {/* Camera icon */}
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-ink-400"
              aria-hidden="true"
            >
              <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider text-center">
              Add photo
            </span>
          </div>
        )}

        {/* Uploading overlay */}
        {state === "uploading" && (
          <div className="absolute inset-0 flex items-center justify-center bg-base/80">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-accent animate-spin"
              aria-hidden="true"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </div>
        )}

        {/* Done checkmark overlay */}
        {state === "done" && (
          <div className="absolute bottom-2 right-2">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-success-bg0">
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="3 7.5 5.5 10 11 4" />
              </svg>
            </span>
          </div>
        )}
      </button>

      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleChange}
        className="hidden"
        aria-hidden="true"
      />

      {/* Activity label */}
      <p className="font-sora text-xs text-ink-100 font-medium truncate text-center">
        {slot.activityName}
      </p>

      {/* Error message */}
      {error && (
        <p className="font-dm-mono text-[10px] text-error text-center" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------- PhotoStrip ----------

export function PhotoStrip({ tripId, slots, onUpload }: PhotoStripProps) {
  if (slots.length === 0) return null;

  return (
    <section className="space-y-3" aria-label="Upload trip photos">
      <div className="flex items-center justify-between">
        <h2 className="font-sora text-lg font-semibold text-ink-100">
          Trip Photos
        </h2>
        <span className="font-dm-mono text-[10px] text-ink-400 uppercase tracking-wider">
          {slots.length} slot{slots.length !== 1 ? "s" : ""}
        </span>
      </div>
      <p className="font-dm-mono text-xs text-ink-400">
        Add a photo from each activity -- max 10MB, JPEG / PNG / WebP
      </p>
      <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-none">
        {slots.map((slot) => (
          <SlotUploadCard
            key={slot.slotId}
            slot={slot}
            tripId={tripId}
            onUpload={onUpload}
          />
        ))}
      </div>
    </section>
  );
}
