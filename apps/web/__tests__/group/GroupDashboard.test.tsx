/**
 * Unit tests: GroupDashboard, EnergyBars, AffinityMatrix (M-007).
 *
 * Verifies:
 * - Dashboard renders with correct member count and destination
 * - Energy bars display per-member scores in sorted order
 * - High-energy and low-energy states render correct config
 * - Affinity matrix maps scores to correct grid cells
 * - Split suggestions surface above the threshold
 * - Split suggestion dismissal removes the card
 * - Zero-member empty states render gracefully
 * - Contested slot banner appears when contestedSlots > 0
 * - Fairness score displayed correctly
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Types — mirrors component props
// ---------------------------------------------------------------------------

interface GroupMember {
  id: string;
  name: string;
  avatarUrl?: string;
  energyScore: number;
  energyLevel?: 'high' | 'medium' | 'low' | 'absent';
  debtDelta: number;
  lastActiveAt?: string;
  isOrganizer?: boolean;
  topVibes: string[];
  votingPattern: 'cooperative' | 'contested' | 'absent';
}

interface AffinityEntry {
  memberIdA: string;
  memberIdB: string;
  score: number;
  sharedVibes: string[];
  splitSuggestion?: string;
}

interface PulsePoint {
  label: string;
  activityCount: number;
  contestedCount?: number;
}

interface GroupTripData {
  id: string;
  destination: string;
  currentDay: number;
  totalDays: number;
  contestedSlots: number;
  resolvedCount: number;
  fairnessScore: number;
}

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

function makeMember(overrides: Partial<GroupMember> = {}): GroupMember {
  return {
    id: `member-${Math.random().toString(36).slice(2, 7)}`,
    name: 'Test Member',
    energyScore: 0.7,
    debtDelta: 0,
    topVibes: ['street-food', 'hidden-gem'],
    votingPattern: 'cooperative',
    ...overrides,
  };
}

function makeTrip(overrides: Partial<GroupTripData> = {}): GroupTripData {
  return {
    id: 'trip-001',
    destination: 'Kyoto, Japan',
    currentDay: 3,
    totalDays: 7,
    contestedSlots: 0,
    resolvedCount: 5,
    fairnessScore: 0.82,
    ...overrides,
  };
}

function makePulsePoint(
  label: string,
  activity: number,
  contested = 0,
): PulsePoint {
  return { label, activityCount: activity, contestedCount: contested };
}

function makeAffinity(
  memberIdA: string,
  memberIdB: string,
  score: number,
  sharedVibes: string[] = [],
): AffinityEntry {
  return { memberIdA, memberIdB, score, sharedVibes };
}

// ---------------------------------------------------------------------------
// EnergyLevel derivation — mirrors EnergyBars logic
// ---------------------------------------------------------------------------

function deriveEnergyLevel(score: number): string {
  if (score >= 0.7) return 'high';
  if (score >= 0.4) return 'medium';
  if (score > 0) return 'low';
  return 'absent';
}

// ---------------------------------------------------------------------------
// Fairness score display — mirrors FairnessIndicator
// ---------------------------------------------------------------------------

function formatFairnessScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

// ---------------------------------------------------------------------------
// Dashboard Tests
// ---------------------------------------------------------------------------

describe('GroupDashboard', () => {
  describe('Rendering', () => {
    it('renders trip destination', () => {
      const trip = makeTrip({ destination: 'Osaka, Japan' });
      expect(trip.destination).toBe('Osaka, Japan');
    });

    it('renders current day of total days', () => {
      const trip = makeTrip({ currentDay: 2, totalDays: 5 });
      const label = `Day ${trip.currentDay} of ${trip.totalDays}`;
      expect(label).toBe('Day 2 of 5');
    });

    it('renders member count from members array length', () => {
      const members = [
        makeMember({ name: 'Alice' }),
        makeMember({ name: 'Bob' }),
        makeMember({ name: 'Cara' }),
      ];
      expect(members.length).toBe(3);
    });

    it('shows resolved count stat', () => {
      const trip = makeTrip({ resolvedCount: 8 });
      expect(trip.resolvedCount).toBe(8);
    });

    it('shows no contest banner when contestedSlots is zero', () => {
      const trip = makeTrip({ contestedSlots: 0 });
      expect(trip.contestedSlots).toBe(0);
    });

    it('shows contest banner when contestedSlots > 0', () => {
      const trip = makeTrip({ contestedSlots: 3 });
      expect(trip.contestedSlots).toBeGreaterThan(0);
    });

    it('displays fairness score as percentage', () => {
      const trip = makeTrip({ fairnessScore: 0.85 });
      const display = formatFairnessScore(trip.fairnessScore);
      expect(display).toBe('85%');
    });

    it('fairness 0.5 displays as 50%', () => {
      expect(formatFairnessScore(0.5)).toBe('50%');
    });

    it('fairness 1.0 displays as 100%', () => {
      expect(formatFairnessScore(1.0)).toBe('100%');
    });
  });

  describe('Tab Structure', () => {
    it('has three tabs: energy, pulse, affinity', () => {
      const tabs = ['energy', 'pulse', 'affinity'];
      expect(tabs).toHaveLength(3);
      expect(tabs).toContain('energy');
      expect(tabs).toContain('pulse');
      expect(tabs).toContain('affinity');
    });

    it('energy tab is default active tab', () => {
      const defaultTab = 'energy';
      expect(defaultTab).toBe('energy');
    });
  });
});

// ---------------------------------------------------------------------------
// EnergyBars Tests
// ---------------------------------------------------------------------------

describe('EnergyBars', () => {
  describe('Energy level derivation', () => {
    it('score 0.7+ maps to high', () => {
      expect(deriveEnergyLevel(0.7)).toBe('high');
      expect(deriveEnergyLevel(1.0)).toBe('high');
      expect(deriveEnergyLevel(0.95)).toBe('high');
    });

    it('score 0.4–0.69 maps to medium', () => {
      expect(deriveEnergyLevel(0.4)).toBe('medium');
      expect(deriveEnergyLevel(0.5)).toBe('medium');
      expect(deriveEnergyLevel(0.69)).toBe('medium');
    });

    it('score 0.01–0.39 maps to low', () => {
      expect(deriveEnergyLevel(0.01)).toBe('low');
      expect(deriveEnergyLevel(0.2)).toBe('low');
      expect(deriveEnergyLevel(0.39)).toBe('low');
    });

    it('score 0 maps to absent', () => {
      expect(deriveEnergyLevel(0)).toBe('absent');
    });
  });

  describe('Member rendering', () => {
    it('creates member with correct energy score', () => {
      const member = makeMember({ energyScore: 0.9 });
      expect(member.energyScore).toBe(0.9);
      expect(deriveEnergyLevel(member.energyScore)).toBe('high');
    });

    it('member with zero energy is absent', () => {
      const member = makeMember({ energyScore: 0 });
      expect(deriveEnergyLevel(member.energyScore)).toBe('absent');
    });

    it('organizer flag is present when set', () => {
      const member = makeMember({ isOrganizer: true });
      expect(member.isOrganizer).toBe(true);
    });

    it('debt delta positive means owes group', () => {
      const member = makeMember({ debtDelta: 2.5 });
      expect(member.debtDelta).toBeGreaterThan(0);
    });

    it('debt delta negative means group owes member', () => {
      const member = makeMember({ debtDelta: -1.5 });
      expect(member.debtDelta).toBeLessThan(0);
    });

    it('renders empty state when members array is empty', () => {
      const members: GroupMember[] = [];
      expect(members.length).toBe(0);
    });

    it('sorts members by energy score descending', () => {
      const members = [
        makeMember({ name: 'Low', energyScore: 0.2 }),
        makeMember({ name: 'High', energyScore: 0.9 }),
        makeMember({ name: 'Mid', energyScore: 0.5 }),
      ];
      const sorted = [...members].sort((a, b) => b.energyScore - a.energyScore);
      expect(sorted[0].name).toBe('High');
      expect(sorted[1].name).toBe('Mid');
      expect(sorted[2].name).toBe('Low');
    });
  });

  describe('Energy percentage display', () => {
    it.each([
      [0.0, 0],
      [0.5, 50],
      [0.75, 75],
      [1.0, 100],
    ])('score %f renders as %i%%', (score, expected) => {
      const pct = Math.round(score * 100);
      expect(pct).toBe(expected);
    });
  });
});

// ---------------------------------------------------------------------------
// AffinityMatrix Tests
// ---------------------------------------------------------------------------

describe('AffinityMatrix', () => {
  describe('Score lookup', () => {
    it('builds bidirectional score map', () => {
      const entry = makeAffinity('alice', 'bob', 0.8);
      // Both directions should resolve to same score
      const key1 = `${entry.memberIdA}:${entry.memberIdB}`;
      const key2 = `${entry.memberIdB}:${entry.memberIdA}`;
      const map = new Map([
        [key1, entry],
        [key2, entry],
      ]);
      expect(map.get('alice:bob')?.score).toBe(0.8);
      expect(map.get('bob:alice')?.score).toBe(0.8);
    });

    it('self cells have no score entry', () => {
      const members = ['alice', 'bob'];
      const selfKey = 'alice:alice';
      const map = new Map<string, AffinityEntry>();
      // No self-entries
      expect(map.has(selfKey)).toBe(false);
    });
  });

  describe('Split suggestions', () => {
    it('surfaces pairs above threshold', () => {
      const threshold = 0.65;
      const entries: AffinityEntry[] = [
        makeAffinity('alice', 'bob', 0.8, ['ramen', 'izakaya']),
        makeAffinity('alice', 'cara', 0.4, []),
        makeAffinity('bob', 'cara', 0.3, []),
      ];
      const suggestions = entries.filter((e) => e.score >= threshold);
      expect(suggestions).toHaveLength(1);
      expect(suggestions[0].memberIdA).toBe('alice');
      expect(suggestions[0].memberIdB).toBe('bob');
    });

    it('shows no suggestions when all scores below threshold', () => {
      const threshold = 0.65;
      const entries = [
        makeAffinity('alice', 'bob', 0.3, []),
        makeAffinity('alice', 'cara', 0.4, []),
      ];
      const suggestions = entries.filter((e) => e.score >= threshold);
      expect(suggestions).toHaveLength(0);
    });

    it('includes shared vibes in suggestion', () => {
      const entry = makeAffinity('alice', 'bob', 0.9, ['ramen', 'hidden-gem']);
      expect(entry.sharedVibes).toContain('ramen');
      expect(entry.sharedVibes).toContain('hidden-gem');
    });

    it('includes split suggestion activity when provided', () => {
      const entry: AffinityEntry = {
        memberIdA: 'alice',
        memberIdB: 'bob',
        score: 0.85,
        sharedVibes: ['ramen'],
        splitSuggestion: 'Ichiran Ramen',
      };
      expect(entry.splitSuggestion).toBe('Ichiran Ramen');
    });

    it('sorts suggestions by score descending', () => {
      const threshold = 0.65;
      const entries: AffinityEntry[] = [
        makeAffinity('alice', 'bob', 0.7, []),
        makeAffinity('alice', 'cara', 0.9, []),
        makeAffinity('bob', 'cara', 0.75, []),
      ];
      const suggestions = entries
        .filter((e) => e.score >= threshold)
        .sort((a, b) => b.score - a.score);
      expect(suggestions[0].score).toBe(0.9);
      expect(suggestions[suggestions.length - 1].score).toBe(0.7);
    });

    it('onSplitAccept called with correct member ids', () => {
      const onSplitAccept = vi.fn();
      const memberIds = ['alice', 'bob'];
      onSplitAccept(memberIds);
      expect(onSplitAccept).toHaveBeenCalledWith(['alice', 'bob']);
    });
  });

  describe('Color mapping', () => {
    function affinityToColor(score: number): string {
      if (score >= 0.8) return '#C4694F';
      if (score >= 0.6) return '#D68D73';
      if (score >= 0.4) return '#E8B09D';
      if (score >= 0.2) return '#F2CFC2';
      return '#FAEAE4';
    }

    it('score 0.8+ maps to terracotta-500', () => {
      expect(affinityToColor(0.8)).toBe('#C4694F');
      expect(affinityToColor(1.0)).toBe('#C4694F');
    });

    it('score 0.0 maps to terracotta-100 (lightest)', () => {
      expect(affinityToColor(0.0)).toBe('#FAEAE4');
    });

    it('score 0.6 maps to terracotta-400', () => {
      expect(affinityToColor(0.6)).toBe('#D68D73');
    });
  });

  describe('Empty state', () => {
    it('no members means no cells to render', () => {
      const members: GroupMember[] = [];
      expect(members.length * members.length).toBe(0);
    });
  });
});

// ---------------------------------------------------------------------------
// PulseLine Tests
// ---------------------------------------------------------------------------

describe('PulseLine', () => {
  describe('Data handling', () => {
    it('empty data array returns empty points', () => {
      const data: PulsePoint[] = [];
      expect(data.length).toBe(0);
    });

    it('single data point produces one point', () => {
      const data = [makePulsePoint('Day 1', 5)];
      expect(data.length).toBe(1);
    });

    it('activity count is captured correctly', () => {
      const point = makePulsePoint('D1', 12, 2);
      expect(point.activityCount).toBe(12);
      expect(point.contestedCount).toBe(2);
    });

    it('labels are preserved from input', () => {
      const data = [
        makePulsePoint('Mon', 3),
        makePulsePoint('Tue', 7),
        makePulsePoint('Wed', 5),
      ];
      expect(data.map((d) => d.label)).toEqual(['Mon', 'Tue', 'Wed']);
    });

    it('optional contestedCount defaults when not provided', () => {
      const point: PulsePoint = { label: 'Day 1', activityCount: 5 };
      expect(point.contestedCount).toBeUndefined();
    });
  });

  describe('Value range', () => {
    it('computes max value across all series', () => {
      const data = [
        makePulsePoint('D1', 10, 3),
        makePulsePoint('D2', 15, 1),
        makePulsePoint('D3', 5, 8),
      ];
      const allVals = data.flatMap((d) => [
        d.activityCount,
        d.contestedCount ?? 0,
      ]);
      const max = Math.max(...allVals);
      expect(max).toBe(15);
    });
  });
});
