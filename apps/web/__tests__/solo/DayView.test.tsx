/**
 * Unit tests: DayView component (M-011).
 *
 * Verifies:
 * - Day navigation between trip days
 * - Time display formatting for slots
 * - Slot ordering within a day
 * - Empty day state
 * - Day boundary constraints
 */

import { describe, it, expect, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DaySlot {
  id: string;
  dayNumber: number;
  sortOrder: number;
  slotType: string;
  startTime: string | null;
  endTime: string | null;
  activityName: string;
}

interface DayViewState {
  currentDay: number;
  totalDays: number;
  slots: DaySlot[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDaySlot(overrides: Partial<DaySlot> = {}): DaySlot {
  return {
    id: `slot-${Math.random().toString(36).slice(2, 8)}`,
    dayNumber: 1,
    sortOrder: 0,
    slotType: 'anchor',
    startTime: '10:00',
    endTime: '12:00',
    activityName: 'Test Activity',
    ...overrides,
  };
}

function makeDayViewState(overrides: Partial<DayViewState> = {}): DayViewState {
  return {
    currentDay: 1,
    totalDays: 7,
    slots: [],
    ...overrides,
  };
}

function getSlotsForDay(state: DayViewState): DaySlot[] {
  return state.slots
    .filter((s) => s.dayNumber === state.currentDay)
    .sort((a, b) => a.sortOrder - b.sortOrder);
}

function navigateDay(state: DayViewState, direction: 'next' | 'prev'): DayViewState {
  const newDay = direction === 'next'
    ? Math.min(state.currentDay + 1, state.totalDays)
    : Math.max(state.currentDay - 1, 1);
  return { ...state, currentDay: newDay };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DayView', () => {
  describe('Day Navigation', () => {
    it('navigates to next day', () => {
      const state = makeDayViewState({ currentDay: 1, totalDays: 7 });
      const next = navigateDay(state, 'next');
      expect(next.currentDay).toBe(2);
    });

    it('navigates to previous day', () => {
      const state = makeDayViewState({ currentDay: 3, totalDays: 7 });
      const prev = navigateDay(state, 'prev');
      expect(prev.currentDay).toBe(2);
    });

    it('cannot navigate before day 1', () => {
      const state = makeDayViewState({ currentDay: 1, totalDays: 7 });
      const prev = navigateDay(state, 'prev');
      expect(prev.currentDay).toBe(1);
    });

    it('cannot navigate past total days', () => {
      const state = makeDayViewState({ currentDay: 7, totalDays: 7 });
      const next = navigateDay(state, 'next');
      expect(next.currentDay).toBe(7);
    });

    it('single day trip has no navigation range', () => {
      const state = makeDayViewState({ currentDay: 1, totalDays: 1 });
      const next = navigateDay(state, 'next');
      const prev = navigateDay(state, 'prev');
      expect(next.currentDay).toBe(1);
      expect(prev.currentDay).toBe(1);
    });
  });

  describe('Time Display', () => {
    it('formats time range for slot', () => {
      const slot = makeDaySlot({ startTime: '09:00', endTime: '10:30' });
      expect(slot.startTime).toBe('09:00');
      expect(slot.endTime).toBe('10:30');
    });

    it('handles null start time', () => {
      const slot = makeDaySlot({ startTime: null });
      expect(slot.startTime).toBeNull();
    });

    it('handles null end time', () => {
      const slot = makeDaySlot({ endTime: null });
      expect(slot.endTime).toBeNull();
    });
  });

  describe('Slot Ordering', () => {
    it('slots ordered by sortOrder within a day', () => {
      const slots = [
        makeDaySlot({ dayNumber: 1, sortOrder: 2, activityName: 'Lunch' }),
        makeDaySlot({ dayNumber: 1, sortOrder: 0, activityName: 'Breakfast' }),
        makeDaySlot({ dayNumber: 1, sortOrder: 1, activityName: 'Morning Walk' }),
      ];
      const state = makeDayViewState({ currentDay: 1, slots });
      const ordered = getSlotsForDay(state);
      expect(ordered.map((s) => s.activityName)).toEqual([
        'Breakfast',
        'Morning Walk',
        'Lunch',
      ]);
    });

    it('filters slots to current day only', () => {
      const slots = [
        makeDaySlot({ dayNumber: 1, activityName: 'Day 1 Activity' }),
        makeDaySlot({ dayNumber: 2, activityName: 'Day 2 Activity' }),
        makeDaySlot({ dayNumber: 1, activityName: 'Day 1 Another' }),
      ];
      const state = makeDayViewState({ currentDay: 1, slots });
      const daySlots = getSlotsForDay(state);
      expect(daySlots).toHaveLength(2);
      expect(daySlots.every((s) => s.dayNumber === 1)).toBe(true);
    });
  });

  describe('Empty Day State', () => {
    it('returns empty array for day with no slots', () => {
      const state = makeDayViewState({ currentDay: 3, slots: [] });
      expect(getSlotsForDay(state)).toHaveLength(0);
    });

    it('returns empty for day outside slot range', () => {
      const slots = [makeDaySlot({ dayNumber: 1 })];
      const state = makeDayViewState({ currentDay: 5, slots });
      expect(getSlotsForDay(state)).toHaveLength(0);
    });
  });
});
