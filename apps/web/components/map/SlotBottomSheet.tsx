"use client";

/**
 * SlotBottomSheet — Mobile bottom sheet for slot detail display.
 *
 * Slides up from bottom on mobile when a map pin is tapped.
 * Shows slot name, type, time, and action buttons (confirm/skip).
 *
 * Usage:
 *   <SlotBottomSheet slot={selectedSlot} onClose={() => setSelected(null)} />
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PinIcon, type SlotType } from "./MapPin";
import type { MapSlot } from "./MapView";

interface SlotBottomSheetProps {
  slot: MapSlot | null;
  onClose: () => void;
  onConfirm?: (slotId: string) => void;
  onSkip?: (slotId: string) => void;
}

export default function SlotBottomSheet({
  slot,
  onClose,
  onConfirm,
  onSkip,
}: SlotBottomSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [translateY, setTranslateY] = useState(0);
  const dragStartY = useRef(0);

  const isOpen = slot !== null;

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Reset translate when slot changes
  useEffect(() => {
    setTranslateY(0);
  }, [slot]);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    setIsDragging(true);
    dragStartY.current = e.touches[0].clientY;
  }, []);

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isDragging) return;
      const delta = e.touches[0].clientY - dragStartY.current;
      // Only allow dragging down
      if (delta > 0) setTranslateY(delta);
    },
    [isDragging]
  );

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false);
    // If dragged more than 100px down, close the sheet
    if (translateY > 100) {
      onClose();
    }
    setTranslateY(0);
  }, [translateY, onClose]);

  if (!isOpen || !slot) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20 lg:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Details for ${slot.name}`}
        className="fixed bottom-0 left-0 right-0 z-50 rounded-t-2xl bg-surface
                   border-t border-ink-700 shadow-lg lg:hidden
                   transition-transform duration-200 ease-out"
        style={{
          transform: `translateY(${translateY}px)`,
          maxHeight: "70vh",
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-2">
          <div className="h-1 w-10 rounded-full bg-ink-700" />
        </div>

        {/* Content */}
        <div className="px-5 pb-6 overflow-y-auto" style={{ maxHeight: "calc(70vh - 40px)" }}>
          {/* Header */}
          <div className="flex items-start gap-3 mb-4">
            <PinIcon slotType={slot.slotType} size={24} />
            <div className="flex-1 min-w-0">
              <h3 className="font-sora font-semibold text-primary text-lg leading-tight truncate">
                {slot.name}
              </h3>
              <span className="font-dm-mono text-xs text-secondary uppercase tracking-wider">
                {slot.slotType}
                {slot.timeLabel ? ` / ${slot.timeLabel}` : ""}
              </span>
            </div>
          </div>

          {/* Description */}
          {slot.description && (
            <p className="text-sm text-secondary leading-relaxed mb-4">
              {slot.description}
            </p>
          )}

          {/* Meta row */}
          {slot.address && (
            <div className="flex items-center gap-2 mb-4 text-sm text-secondary">
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <path
                  d="M7 0C4.243 0 2 2.243 2 5c0 3.75 5 8.25 5 8.25S12 8.75 12 5c0-2.757-2.243-5-5-5zm0 7a2 2 0 110-4 2 2 0 010 4z"
                  fill="currentColor"
                />
              </svg>
              <span className="truncate">{slot.address}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 mt-2">
            {onConfirm && (
              <button
                onClick={() => onConfirm(slot.id)}
                className="btn-primary flex-1 text-sm"
                aria-label={`Confirm ${slot.name}`}
              >
                Confirm
              </button>
            )}
            {onSkip && (
              <button
                onClick={() => onSkip(slot.id)}
                className="btn-secondary flex-1 text-sm"
                aria-label={`Skip ${slot.name}`}
              >
                Skip
              </button>
            )}
            <button
              onClick={onClose}
              className="btn-secondary px-3 text-sm"
              aria-label="Close details"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <path
                  d="M12 4L4 12M4 4l8 8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
