"use client";

import { useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CityCombobox, type CityData } from "./CityCombobox";

export interface LegRowData {
  id: string;
  city: string;
  country: string;
  timezone: string | null;
  destination: string;
  startDate: string;
  endDate: string;
  position: number;
}

interface LegEditorRowProps {
  leg: LegRowData;
  index: number;
  totalLegs: number;
  isEditing: boolean;
  disabled: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: (legId: string, data: Partial<LegRowData>) => Promise<void>;
  onRemove: (legId: string) => void;
  onMoveUp: (legId: string) => void;
  onMoveDown: (legId: string) => void;
}

function GripIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <circle cx="9" cy="6" r="1.5" />
      <circle cx="15" cy="6" r="1.5" />
      <circle cx="9" cy="12" r="1.5" />
      <circle cx="15" cy="12" r="1.5" />
      <circle cx="9" cy="18" r="1.5" />
      <circle cx="15" cy="18" r="1.5" />
    </svg>
  );
}

function ChevronUpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15" />
    </svg>
  );
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function PencilIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

export function LegEditorRow({
  leg,
  index,
  totalLegs,
  isEditing,
  disabled,
  onEdit,
  onCancelEdit,
  onSave,
  onRemove,
  onMoveUp,
  onMoveDown,
}: LegEditorRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: leg.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // Edit mode state
  const [editCity, setEditCity] = useState<CityData | null>(
    isEditing
      ? { slug: "", city: leg.city, state: "", country: leg.country, timezone: leg.timezone ?? "", destination: leg.destination, lat: 0, lng: 0 }
      : null
  );
  const [editStartDate, setEditStartDate] = useState(leg.startDate.split("T")[0]);
  const [editEndDate, setEditEndDate] = useState(leg.endDate.split("T")[0]);
  const [saving, setSaving] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  async function handleSaveEdit() {
    if (!editCity) return;
    setSaving(true);
    try {
      await onSave(leg.id, {
        city: editCity.city,
        country: editCity.country,
        timezone: editCity.timezone || null,
        destination: editCity.destination,
        startDate: new Date(editStartDate).toISOString(),
        endDate: new Date(editEndDate).toISOString(),
      });
    } finally {
      setSaving(false);
    }
  }

  if (isEditing) {
    return (
      <div
        ref={setNodeRef}
        style={style}
        className="rounded-lg border border-accent/30 bg-accent/5 p-4 space-y-3"
      >
        <div className="flex items-center justify-between">
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Editing leg {index + 1}
          </span>
          <button
            onClick={onCancelEdit}
            className="font-sora text-xs text-ink-400 hover:text-ink-100 transition-colors"
          >
            Cancel
          </button>
        </div>

        <CityCombobox
          value={editCity}
          onChange={setEditCity}
          label="City"
          id={`edit-leg-city-${leg.id}`}
        />

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              htmlFor={`edit-leg-start-${leg.id}`}
              className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mb-1.5 block"
            >
              Start
            </label>
            <input
              id={`edit-leg-start-${leg.id}`}
              type="date"
              value={editStartDate}
              onChange={(e) => setEditStartDate(e.target.value)}
              className="w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
            />
          </div>
          <div>
            <label
              htmlFor={`edit-leg-end-${leg.id}`}
              className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mb-1.5 block"
            >
              End
            </label>
            <input
              id={`edit-leg-end-${leg.id}`}
              type="date"
              value={editEndDate}
              min={editStartDate}
              onChange={(e) => setEditEndDate(e.target.value)}
              className="w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={handleSaveEdit}
            disabled={saving || !editCity}
            className="rounded-lg bg-accent px-4 py-2 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed min-h-[40px]"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex items-center gap-2 rounded-lg border border-ink-700 bg-surface p-3 transition-colors ${
        isDragging ? "shadow-lg" : "hover:border-ink-600"
      }`}
      data-testid={`leg-row-${index}`}
    >
      {/* Drag handle */}
      <button
        {...attributes}
        {...listeners}
        className="flex-shrink-0 cursor-grab rounded p-1 text-ink-500 hover:text-ink-300 active:cursor-grabbing"
        aria-label={`Drag to reorder leg ${index + 1}`}
      >
        <GripIcon className="h-4 w-4" />
      </button>

      {/* Position number */}
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-accent/10 text-accent font-dm-mono text-xs flex items-center justify-center font-medium">
        {index + 1}
      </span>

      {/* City info */}
      <div className="flex-1 min-w-0">
        <p className="font-sora text-sm font-medium text-ink-100 truncate">
          {leg.city}
        </p>
        <p className="font-dm-mono text-xs text-ink-400 truncate">
          {leg.country} &middot; {formatDate(leg.startDate)} - {formatDate(leg.endDate)}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {/* Up */}
        <button
          onClick={() => onMoveUp(leg.id)}
          disabled={index === 0 || disabled}
          className="rounded p-1.5 text-ink-500 hover:text-ink-100 hover:bg-base disabled:opacity-30 disabled:cursor-not-allowed transition-colors min-h-[32px] min-w-[32px] flex items-center justify-center"
          aria-label={`Move leg ${index + 1} up`}
          data-testid={`leg-move-up-${index}`}
        >
          <ChevronUpIcon className="h-3.5 w-3.5" />
        </button>

        {/* Down */}
        <button
          onClick={() => onMoveDown(leg.id)}
          disabled={index === totalLegs - 1 || disabled}
          className="rounded p-1.5 text-ink-500 hover:text-ink-100 hover:bg-base disabled:opacity-30 disabled:cursor-not-allowed transition-colors min-h-[32px] min-w-[32px] flex items-center justify-center"
          aria-label={`Move leg ${index + 1} down`}
          data-testid={`leg-move-down-${index}`}
        >
          <ChevronDownIcon className="h-3.5 w-3.5" />
        </button>

        {/* Edit */}
        <button
          onClick={onEdit}
          disabled={disabled}
          className="rounded p-1.5 text-ink-500 hover:text-ink-100 hover:bg-base disabled:opacity-30 transition-colors min-h-[32px] min-w-[32px] flex items-center justify-center"
          aria-label={`Edit leg ${index + 1}`}
          data-testid={`leg-edit-${index}`}
        >
          <PencilIcon className="h-3.5 w-3.5" />
        </button>

        {/* Remove */}
        {confirmRemove ? (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setConfirmRemove(false)}
              className="rounded px-2 py-1 font-dm-mono text-xs text-ink-400 hover:text-ink-100 transition-colors"
            >
              No
            </button>
            <button
              onClick={() => {
                onRemove(leg.id);
                setConfirmRemove(false);
              }}
              disabled={totalLegs <= 1}
              className="rounded px-2 py-1 font-dm-mono text-xs text-red-400 hover:text-red-300 disabled:opacity-30 transition-colors"
            >
              Remove
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmRemove(true)}
            disabled={totalLegs <= 1 || disabled}
            className="rounded p-1.5 text-ink-500 hover:text-red-400 hover:bg-red-400/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors min-h-[32px] min-w-[32px] flex items-center justify-center"
            aria-label={`Remove leg ${index + 1}`}
            data-testid={`leg-remove-${index}`}
          >
            <TrashIcon className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
