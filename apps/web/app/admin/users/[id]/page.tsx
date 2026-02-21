'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserDetail {
  id: string;
  email: string;
  name: string | null;
  avatarUrl: string | null;
  googleId: string | null;
  emailVerified: string | null;
  subscriptionTier: string;
  systemRole: string;
  featureFlags: Record<string, boolean> | null;
  onboardingComplete: boolean;
  accessCohort: string | null;
  stripeCustomerId: string | null;
  stripeSubId: string | null;
  lastActiveAt: string | null;
  createdAt: string;
  updatedAt: string;
}

interface TripSummary {
  id: string;
  destination: string;
  city: string;
  country: string;
  mode: string;
  status: string;
  startDate: string;
  endDate: string;
  createdAt: string;
}

interface SignalRow {
  id: string;
  signalType: string;
  signalValue: number;
  tripPhase: string;
  rawAction: string;
  createdAt: string;
}

interface UserDetailResponse {
  user: UserDetail;
  trips: TripSummary[];
  signalCount: number;
  recentSignals: SignalRow[];
}

const TIER_COLORS: Record<string, string> = {
  free: 'bg-ink-800 text-ink-500',
  beta: 'bg-blue-100 text-blue-800',
  pro: 'bg-purple-100 text-purple-800',
  lifetime: 'bg-amber-100 text-amber-800',
};

const TRIP_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-ink-800 text-ink-500',
  planning: 'bg-yellow-100 text-yellow-800',
  active: 'bg-green-100 text-green-800',
  completed: 'bg-blue-100 text-blue-800',
  archived: 'bg-ink-800 text-ink-500',
};

const VALID_TIERS = ['free', 'beta', 'pro', 'lifetime'] as const;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminUserDetailPage() {
  const params = useParams();
  const userId = params.id as string;

  const [data, setData] = useState<UserDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Feature flag editor
  const [flagEditing, setFlagEditing] = useState(false);
  const [flagDraft, setFlagDraft] = useState<Record<string, boolean>>({});
  const [newFlagName, setNewFlagName] = useState('');
  const [flagSaving, setFlagSaving] = useState(false);
  const [flagMessage, setFlagMessage] = useState<string | null>(null);

  // Tier editor
  const [tierEditing, setTierEditing] = useState(false);
  const [tierDraft, setTierDraft] = useState('');
  const [tierSaving, setTierSaving] = useState(false);
  const [tierMessage, setTierMessage] = useState<string | null>(null);

  const fetchUser = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}`);
      if (!res.ok) throw new Error(`Failed to fetch user: ${res.status}`);
      const json: UserDetailResponse = await res.json();
      setData(json);
      setFlagDraft(json.user.featureFlags ?? {});
      setTierDraft(json.user.subscriptionTier);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // ------ Feature flag handlers ------

  const handleFlagToggle = (name: string) => {
    setFlagDraft((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const handleAddFlag = () => {
    const name = newFlagName.trim().replace(/\s+/g, '_').toLowerCase();
    if (!name || name in flagDraft) return;
    setFlagDraft((prev) => ({ ...prev, [name]: true }));
    setNewFlagName('');
  };

  const handleRemoveFlag = (name: string) => {
    setFlagDraft((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const saveFlags = async () => {
    setFlagSaving(true);
    setFlagMessage(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}/feature-flags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flags: flagDraft }),
      });
      if (!res.ok) throw new Error(`Failed to save flags: ${res.status}`);
      setFlagMessage('Feature flags updated');
      setFlagEditing(false);
      fetchUser();
    } catch (err: any) {
      setFlagMessage(`Error: ${err.message}`);
    } finally {
      setFlagSaving(false);
    }
  };

  // ------ Tier handlers ------

  const saveTier = async () => {
    setTierSaving(true);
    setTierMessage(null);
    try {
      const res = await fetch(`/api/admin/users/${userId}/subscription-tier`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: tierDraft }),
      });
      if (!res.ok) throw new Error(`Failed to update tier: ${res.status}`);
      setTierMessage('Subscription tier updated');
      setTierEditing(false);
      fetchUser();
    } catch (err: any) {
      setTierMessage(`Error: ${err.message}`);
    } finally {
      setTierSaving(false);
    }
  };

  // ------ Loading / Error states ------

  if (loading && !data) {
    return (
      <div className="py-12 text-center font-mono text-sm text-ink-600">
        Loading user...
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded border border-error/30 bg-error-bg px-4 py-3">
        <p className="font-mono text-sm text-error">{error}</p>
        <a
          href="/admin/users"
          className="mt-2 inline-block font-mono text-xs text-accent hover:underline"
        >
          Back to Users
        </a>
      </div>
    );
  }

  if (!data) return null;

  const { user, trips, signalCount, recentSignals } = data;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="font-mono text-xs text-ink-600">
        <a href="/admin/users" className="hover:text-accent">
          Users
        </a>
        <span className="mx-1">/</span>
        <span className="text-ink-500">{user.email}</span>
      </div>

      {/* Header */}
      <div className="flex items-start gap-4">
        {user.avatarUrl ? (
          <img
            src={user.avatarUrl}
            alt=""
            className="h-16 w-16 rounded-full"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-base font-display text-xl text-ink-600">
            {(user.name ?? user.email)[0].toUpperCase()}
          </div>
        )}
        <div className="flex-1">
          <h2 className="font-display text-2xl text-ink-100">
            {user.name ?? 'Unnamed User'}
          </h2>
          <p className="font-mono text-sm text-ink-500">{user.email}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <span
              className={`rounded px-2 py-0.5 text-xs ${
                TIER_COLORS[user.subscriptionTier] ?? 'bg-ink-800 text-ink-500'
              }`}
            >
              {user.subscriptionTier}
            </span>
            {user.systemRole === 'admin' && (
              <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-error">
                admin
              </span>
            )}
            {user.onboardingComplete && (
              <span className="rounded bg-green-50 px-2 py-0.5 text-xs text-green-700">
                onboarded
              </span>
            )}
          </div>
        </div>
        <span className="font-mono text-xs text-ink-600">
          ID: {user.id.slice(0, 8)}
        </span>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 gap-4 rounded-lg border border-ink-700 bg-surface p-4 lg:grid-cols-4">
        <div>
          <span className="font-mono text-xs text-ink-600">Joined</span>
          <p className="font-mono text-sm text-ink-100">
            {new Date(user.createdAt).toLocaleDateString()}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Last Active</span>
          <p className="font-mono text-sm text-ink-100">
            {user.lastActiveAt
              ? new Date(user.lastActiveAt).toLocaleDateString()
              : '--'}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Trips</span>
          <p className="font-mono text-sm text-ink-100">{trips.length}</p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Signals</span>
          <p className="font-mono text-sm text-ink-100">
            {signalCount.toLocaleString()}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Google ID</span>
          <p className="font-mono text-sm text-ink-100 truncate">
            {user.googleId ?? '--'}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Stripe</span>
          <p className="font-mono text-sm text-ink-100 truncate">
            {user.stripeCustomerId ?? '--'}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Access Cohort</span>
          <p className="font-mono text-sm text-ink-100">
            {user.accessCohort ?? '--'}
          </p>
        </div>
        <div>
          <span className="font-mono text-xs text-ink-600">Email Verified</span>
          <p className="font-mono text-sm text-ink-100">
            {user.emailVerified
              ? new Date(user.emailVerified).toLocaleDateString()
              : '--'}
          </p>
        </div>
      </div>

      {/* Subscription Tier */}
      <section className="rounded-lg border border-ink-700 bg-surface p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg text-ink-100">
            Subscription Tier
          </h3>
          {!tierEditing && (
            <button
              onClick={() => setTierEditing(true)}
              className="font-mono text-xs text-accent hover:underline"
            >
              Change
            </button>
          )}
        </div>

        {tierEditing ? (
          <div className="mt-3 space-y-3">
            <div className="flex gap-2">
              {VALID_TIERS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTierDraft(t)}
                  className={`rounded px-3 py-1.5 font-mono text-xs capitalize transition-colors ${
                    tierDraft === t
                      ? 'bg-accent text-white'
                      : 'border border-ink-700 bg-base text-ink-500 hover:bg-ink-800'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={saveTier}
                disabled={tierSaving || tierDraft === user.subscriptionTier}
                className="rounded bg-ink-200 px-3 py-1.5 font-mono text-xs text-white hover:bg-ink-300 disabled:opacity-40"
              >
                {tierSaving ? 'Saving...' : 'Save Tier'}
              </button>
              <button
                onClick={() => {
                  setTierEditing(false);
                  setTierDraft(user.subscriptionTier);
                }}
                className="font-mono text-xs text-ink-500 hover:text-ink-300"
              >
                Cancel
              </button>
            </div>
            {tierMessage && (
              <p
                className={`font-mono text-xs ${
                  tierMessage.startsWith('Error') ? 'text-error' : 'text-green-600'
                }`}
              >
                {tierMessage}
              </p>
            )}
          </div>
        ) : (
          <div className="mt-2">
            <span
              className={`rounded px-2 py-1 text-sm ${
                TIER_COLORS[user.subscriptionTier] ?? 'bg-ink-800 text-ink-500'
              }`}
            >
              {user.subscriptionTier}
            </span>
            {tierMessage && (
              <p className="mt-2 font-mono text-xs text-green-600">
                {tierMessage}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Feature Flags */}
      <section className="rounded-lg border border-ink-700 bg-surface p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg text-ink-100">
            Feature Flags
          </h3>
          {!flagEditing && (
            <button
              onClick={() => {
                setFlagEditing(true);
                setFlagDraft(user.featureFlags ?? {});
              }}
              className="font-mono text-xs text-accent hover:underline"
            >
              Edit
            </button>
          )}
        </div>

        {flagEditing ? (
          <div className="mt-3 space-y-3">
            {/* Existing flags */}
            {Object.keys(flagDraft).length > 0 ? (
              <div className="space-y-1.5">
                {Object.entries(flagDraft).map(([name, enabled]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded bg-base px-3 py-1.5"
                  >
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleFlagToggle(name)}
                        className={`h-4 w-8 rounded-full transition-colors ${
                          enabled ? 'bg-green-500' : 'bg-ink-700'
                        }`}
                      >
                        <span
                          className={`block h-3 w-3 rounded-full bg-white transition-transform ${
                            enabled ? 'translate-x-4' : 'translate-x-0.5'
                          }`}
                        />
                      </button>
                      <span className="font-mono text-sm text-ink-300">
                        {name}
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveFlag(name)}
                      className="font-mono text-xs text-red-500 hover:text-error"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="font-mono text-xs text-ink-600">
                No flags set
              </p>
            )}

            {/* Add new flag */}
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="new_flag_name"
                value={newFlagName}
                onChange={(e) => setNewFlagName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddFlag()}
                className="flex-1 rounded border border-ink-700 bg-base px-2 py-1 font-mono text-sm focus:border-accent focus:outline-none"
              />
              <button
                onClick={handleAddFlag}
                disabled={!newFlagName.trim()}
                className="rounded border border-ink-700 bg-base px-2 py-1 font-mono text-xs text-ink-500 hover:bg-ink-800 disabled:opacity-40"
              >
                Add Flag
              </button>
            </div>

            {/* Save / Cancel */}
            <div className="flex items-center gap-2">
              <button
                onClick={saveFlags}
                disabled={flagSaving}
                className="rounded bg-ink-200 px-3 py-1.5 font-mono text-xs text-white hover:bg-ink-300 disabled:opacity-40"
              >
                {flagSaving ? 'Saving...' : 'Save Flags'}
              </button>
              <button
                onClick={() => {
                  setFlagEditing(false);
                  setFlagDraft(user.featureFlags ?? {});
                }}
                className="font-mono text-xs text-ink-500 hover:text-ink-300"
              >
                Cancel
              </button>
            </div>
            {flagMessage && (
              <p
                className={`font-mono text-xs ${
                  flagMessage.startsWith('Error') ? 'text-error' : 'text-green-600'
                }`}
              >
                {flagMessage}
              </p>
            )}
          </div>
        ) : (
          <div className="mt-2">
            {user.featureFlags &&
            Object.keys(user.featureFlags).length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(user.featureFlags).map(([name, enabled]) => (
                  <span
                    key={name}
                    className={`rounded px-2 py-0.5 font-mono text-xs ${
                      enabled
                        ? 'bg-green-50 text-green-700'
                        : 'bg-ink-800 text-ink-600 line-through'
                    }`}
                  >
                    {name}
                  </span>
                ))}
              </div>
            ) : (
              <p className="font-mono text-xs text-ink-600">No flags set</p>
            )}
            {flagMessage && (
              <p className="mt-2 font-mono text-xs text-green-600">
                {flagMessage}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Trips */}
      <section className="rounded-lg border border-ink-700 bg-surface p-4">
        <h3 className="mb-3 font-display text-lg text-ink-100">
          Trips ({trips.length})
        </h3>
        {trips.length === 0 ? (
          <p className="font-mono text-xs text-ink-600">No trips yet</p>
        ) : (
          <div className="space-y-2">
            {trips.map((trip) => (
              <div
                key={trip.id}
                className="flex items-center justify-between rounded bg-base px-3 py-2"
              >
                <div>
                  <span className="font-mono text-sm text-ink-100">
                    {trip.destination}
                  </span>
                  <span className="ml-2 font-mono text-xs text-ink-600">
                    {trip.city}, {trip.country}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-ink-600">
                    {trip.mode}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      TRIP_STATUS_COLORS[trip.status] ?? 'bg-ink-800 text-ink-500'
                    }`}
                  >
                    {trip.status}
                  </span>
                  <span className="font-mono text-xs text-ink-600">
                    {new Date(trip.startDate).toLocaleDateString()} --{' '}
                    {new Date(trip.endDate).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Recent Signals */}
      <section className="rounded-lg border border-ink-700 bg-surface p-4">
        <h3 className="mb-3 font-display text-lg text-ink-100">
          Recent Signals ({signalCount.toLocaleString()} total)
        </h3>
        {recentSignals.length === 0 ? (
          <p className="font-mono text-xs text-ink-600">
            No behavioral signals recorded
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-xs">
              <thead>
                <tr className="border-b border-ink-700 text-left text-ink-600">
                  <th className="px-2 py-1.5">Type</th>
                  <th className="px-2 py-1.5">Value</th>
                  <th className="px-2 py-1.5">Phase</th>
                  <th className="px-2 py-1.5">Action</th>
                  <th className="px-2 py-1.5">Time</th>
                </tr>
              </thead>
              <tbody>
                {recentSignals.map((s) => (
                  <tr
                    key={s.id}
                    className="border-b border-ink-700/30 text-ink-500"
                  >
                    <td className="px-2 py-1.5">{s.signalType}</td>
                    <td className="px-2 py-1.5">
                      <span
                        className={
                          s.signalValue > 0
                            ? 'text-green-600'
                            : s.signalValue < 0
                              ? 'text-error'
                              : ''
                        }
                      >
                        {s.signalValue.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-2 py-1.5">{s.tripPhase}</td>
                    <td className="max-w-[200px] truncate px-2 py-1.5">
                      {s.rawAction}
                    </td>
                    <td className="px-2 py-1.5 text-ink-600">
                      {new Date(s.createdAt).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
