"use client";

import { useState, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { LegEditorRow, type LegRowData } from "./LegEditorRow";
import { CityCombobox, type CityData } from "./CityCombobox";
import { MAX_LEGS } from "@/lib/constants/trip";

interface LegEditorProps {
  tripId: string;
  legs: LegRowData[];
  tripStatus: string;
  isOrganizer: boolean;
  onLegsChange: () => void;
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function LegEditor({
  tripId,
  legs,
  tripStatus,
  isOrganizer,
  onLegsChange,
}: LegEditorProps) {
  const [editingLegId, setEditingLegId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addCity, setAddCity] = useState<CityData | null>(null);
  const [addStartDate, setAddStartDate] = useState("");
  const [addEndDate, setAddEndDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit =
    isOrganizer && (tripStatus === "draft" || tripStatus === "planning");

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const reorderLegs = useCallback(
    async (newOrder: string[]) => {
      setError(null);
      try {
        const res = await fetch(`/api/trips/${tripId}/legs/reorder`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ legOrder: newOrder }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error || "Failed to reorder legs");
        }
        onLegsChange();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to reorder");
      }
    },
    [tripId, onLegsChange]
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = legs.findIndex((l) => l.id === active.id);
    const newIndex = legs.findIndex((l) => l.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    // Build new order
    const ids = legs.map((l) => l.id);
    ids.splice(oldIndex, 1);
    ids.splice(newIndex, 0, active.id as string);
    reorderLegs(ids);
  }

  const handleMoveUp = useCallback(
    (legId: string) => {
      const idx = legs.findIndex((l) => l.id === legId);
      if (idx <= 0) return;
      const ids = legs.map((l) => l.id);
      [ids[idx - 1], ids[idx]] = [ids[idx], ids[idx - 1]];
      reorderLegs(ids);
    },
    [legs, reorderLegs]
  );

  const handleMoveDown = useCallback(
    (legId: string) => {
      const idx = legs.findIndex((l) => l.id === legId);
      if (idx === -1 || idx >= legs.length - 1) return;
      const ids = legs.map((l) => l.id);
      [ids[idx], ids[idx + 1]] = [ids[idx + 1], ids[idx]];
      reorderLegs(ids);
    },
    [legs, reorderLegs]
  );

  const handleSaveLeg = useCallback(
    async (legId: string, data: Partial<LegRowData>) => {
      setError(null);
      try {
        const res = await fetch(`/api/trips/${tripId}/legs/${legId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || "Failed to update leg");
        }
        setEditingLegId(null);
        onLegsChange();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update leg");
      }
    },
    [tripId, onLegsChange]
  );

  const handleRemoveLeg = useCallback(
    async (legId: string) => {
      setError(null);
      try {
        const res = await fetch(`/api/trips/${tripId}/legs/${legId}`, {
          method: "DELETE",
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || "Failed to remove leg");
        }
        onLegsChange();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to remove leg");
      }
    },
    [tripId, onLegsChange]
  );

  async function handleAddLeg() {
    if (!addCity || !addStartDate || !addEndDate) return;

    setSaving(true);
    setError(null);

    try {
      const res = await fetch(`/api/trips/${tripId}/legs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          city: addCity.city,
          country: addCity.country,
          timezone: addCity.timezone || undefined,
          destination: addCity.destination,
          startDate: new Date(addStartDate).toISOString(),
          endDate: new Date(addEndDate).toISOString(),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to add leg");
      }

      setShowAddForm(false);
      setAddCity(null);
      setAddStartDate("");
      setAddEndDate("");
      onLegsChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add leg");
    } finally {
      setSaving(false);
    }
  }

  // Default add form dates to day after last leg's end
  function openAddForm() {
    if (legs.length > 0) {
      const lastLeg = legs[legs.length - 1];
      const lastEnd = new Date(lastLeg.endDate);
      const nextStart = new Date(lastEnd);
      nextStart.setDate(nextStart.getDate() + 1);
      setAddStartDate(nextStart.toISOString().split("T")[0]);
      const nextEnd = new Date(nextStart);
      nextEnd.setDate(nextEnd.getDate() + 3);
      setAddEndDate(nextEnd.toISOString().split("T")[0]);
    }
    setShowAddForm(true);
  }

  return (
    <div className="space-y-3" data-testid="leg-editor">
      <div className="flex items-center justify-between">
        <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
          Cities ({legs.length}/{MAX_LEGS})
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2">
          <p className="font-dm-mono text-xs text-red-400">{error}</p>
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={legs.map((l) => l.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-2">
            {legs.map((leg, i) => (
              <LegEditorRow
                key={leg.id}
                leg={leg}
                index={i}
                totalLegs={legs.length}
                isEditing={editingLegId === leg.id}
                disabled={!canEdit}
                onEdit={() => setEditingLegId(leg.id)}
                onCancelEdit={() => setEditingLegId(null)}
                onSave={handleSaveLeg}
                onRemove={handleRemoveLeg}
                onMoveUp={handleMoveUp}
                onMoveDown={handleMoveDown}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {/* Add form */}
      {showAddForm && (
        <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 space-y-3">
          <span className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider">
            Add city
          </span>

          <CityCombobox
            value={addCity}
            onChange={setAddCity}
            id="add-leg-city"
          />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="add-leg-start"
                className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mb-1.5 block"
              >
                Start
              </label>
              <input
                id="add-leg-start"
                type="date"
                value={addStartDate}
                onChange={(e) => setAddStartDate(e.target.value)}
                className="w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
              />
            </div>
            <div>
              <label
                htmlFor="add-leg-end"
                className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mb-1.5 block"
              >
                End
              </label>
              <input
                id="add-leg-end"
                type="date"
                value={addEndDate}
                min={addStartDate}
                onChange={(e) => setAddEndDate(e.target.value)}
                className="w-full rounded-lg border border-ink-700 bg-base px-3 py-2 font-dm-mono text-sm text-ink-100 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => {
                setShowAddForm(false);
                setAddCity(null);
                setAddStartDate("");
                setAddEndDate("");
              }}
              className="rounded-lg px-3 py-2 font-sora text-sm text-ink-400 hover:text-ink-100 transition-colors min-h-[40px]"
            >
              Cancel
            </button>
            <button
              onClick={handleAddLeg}
              disabled={saving || !addCity || !addStartDate || !addEndDate}
              className="rounded-lg bg-accent px-4 py-2 font-sora text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed min-h-[40px]"
            >
              {saving ? "Adding..." : "Add city"}
            </button>
          </div>
        </div>
      )}

      {/* Add button */}
      {canEdit && !showAddForm && legs.length < MAX_LEGS && (
        <button
          onClick={openAddForm}
          className="w-full rounded-lg border border-dashed border-ink-700 px-4 py-3 font-sora text-sm text-ink-400 hover:text-ink-100 hover:border-ink-600 transition-colors flex items-center justify-center gap-2 min-h-[44px]"
          data-testid="add-leg-button"
        >
          <PlusIcon className="h-4 w-4" />
          Add city
        </button>
      )}
    </div>
  );
}
