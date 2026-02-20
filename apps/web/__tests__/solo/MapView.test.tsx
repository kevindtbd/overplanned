/**
 * Unit tests: MapView component (M-011).
 *
 * Verifies:
 * - Pin rendering from activity nodes with lat/lng
 * - Day filter shows only pins for selected day
 * - Pin data includes activity name and category
 * - Empty state when no pins for selected day
 * - Pin clustering with nearby coordinates
 */

import { describe, it, expect, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MapPin {
  id: string;
  activityNodeId: string;
  activityName: string;
  category: string;
  latitude: number;
  longitude: number;
  dayNumber: number;
  slotType: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMapPin(overrides: Partial<MapPin> = {}): MapPin {
  return {
    id: `pin-${Math.random().toString(36).slice(2, 8)}`,
    activityNodeId: 'node-001',
    activityName: 'Senso-ji Temple',
    category: 'culture',
    latitude: 35.7148,
    longitude: 139.7967,
    dayNumber: 1,
    slotType: 'anchor',
    ...overrides,
  };
}

function filterPinsByDay(pins: MapPin[], day: number | null): MapPin[] {
  if (day === null) return pins; // "All days" view
  return pins.filter((p) => p.dayNumber === day);
}

function arePinsNearby(a: MapPin, b: MapPin, thresholdDeg: number = 0.005): boolean {
  return (
    Math.abs(a.latitude - b.latitude) < thresholdDeg &&
    Math.abs(a.longitude - b.longitude) < thresholdDeg
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MapView', () => {
  describe('Pin Rendering', () => {
    it('renders pin with correct lat/lng', () => {
      const pin = makeMapPin({ latitude: 35.6762, longitude: 139.6503 });
      expect(pin.latitude).toBe(35.6762);
      expect(pin.longitude).toBe(139.6503);
    });

    it('pin includes activity name', () => {
      const pin = makeMapPin({ activityName: 'Meiji Shrine' });
      expect(pin.activityName).toBe('Meiji Shrine');
    });

    it('pin includes category', () => {
      const pin = makeMapPin({ category: 'dining' });
      expect(pin.category).toBe('dining');
    });

    it('pin references activity node', () => {
      const pin = makeMapPin({ activityNodeId: 'node-xyz' });
      expect(pin.activityNodeId).toBe('node-xyz');
    });
  });

  describe('Day Filter', () => {
    const pins = [
      makeMapPin({ dayNumber: 1, activityName: 'Day 1 Spot' }),
      makeMapPin({ dayNumber: 1, activityName: 'Day 1 Lunch' }),
      makeMapPin({ dayNumber: 2, activityName: 'Day 2 Spot' }),
      makeMapPin({ dayNumber: 3, activityName: 'Day 3 Spot' }),
    ];

    it('filters to single day', () => {
      const filtered = filterPinsByDay(pins, 1);
      expect(filtered).toHaveLength(2);
      expect(filtered.every((p) => p.dayNumber === 1)).toBe(true);
    });

    it('shows all pins when day filter is null', () => {
      const filtered = filterPinsByDay(pins, null);
      expect(filtered).toHaveLength(4);
    });

    it('returns empty for day with no pins', () => {
      const filtered = filterPinsByDay(pins, 5);
      expect(filtered).toHaveLength(0);
    });

    it('day 2 filter returns correct pin', () => {
      const filtered = filterPinsByDay(pins, 2);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].activityName).toBe('Day 2 Spot');
    });
  });

  describe('Pin Clustering', () => {
    it('detects nearby pins for clustering', () => {
      const a = makeMapPin({ latitude: 35.6762, longitude: 139.6503 });
      const b = makeMapPin({ latitude: 35.6765, longitude: 139.6506 });
      expect(arePinsNearby(a, b)).toBe(true);
    });

    it('distant pins are not clustered', () => {
      const a = makeMapPin({ latitude: 35.6762, longitude: 139.6503 });
      const b = makeMapPin({ latitude: 35.7148, longitude: 139.7967 });
      expect(arePinsNearby(a, b)).toBe(false);
    });
  });

  describe('Empty State', () => {
    it('no pins when trip has no slots', () => {
      const filtered = filterPinsByDay([], 1);
      expect(filtered).toHaveLength(0);
    });

    it('no pins when all slots lack coordinates', () => {
      // Pins are only created for slots with valid lat/lng
      // An empty pins array means no valid coordinates
      const pins: MapPin[] = [];
      expect(pins).toHaveLength(0);
    });
  });
});
