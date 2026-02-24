"use client";

import { useState, useCallback, useEffect } from "react";

// ---------- Types for API response ----------

export interface ApiSlot {
  id: string;
  dayNumber: number;
  sortOrder: number;
  slotType: string;
  status: string;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number | null;
  isLocked: boolean;
  // voteState stores group vote data as JSON (nullable)
  voteState: Record<string, unknown> | null;
  activityNode: {
    id: string;
    name: string;
    category: string;
    latitude: number;
    longitude: number;
    priceLevel: number | null;
    primaryImageUrl?: string | null;
  } | null;
}

export interface ApiLeg {
  id: string;
  position: number;
  city: string;
  country: string;
  timezone: string | null;
  destination: string;
  startDate: string;
  endDate: string;
}

export interface ApiTrip {
  id: string;
  name: string | null;
  startDate: string;
  endDate: string;
  mode: string;
  status: string;
  planningProgress: number;
  packingList: {
    items: Array<{
      id: string;
      text: string;
      category: "essentials" | "clothing" | "documents" | "tech" | "toiletries" | "misc";
      checked: boolean;
    }>;
    generatedAt: string;
    model: string;
  } | null;
  legs: ApiLeg[];
  slots: ApiSlot[];
  members: {
    id: string;
    userId: string;
    role: string;
    status: string;
    joinedAt: string;
    user: {
      id: string;
      name: string | null;
      avatarUrl: string | null;
    };
  }[];
  // Derived from legs[0] for convenience
  city: string;
  country: string;
  destination: string;
  timezone: string;
}

export type FetchState = "loading" | "error" | "success";

export interface ReflectionSummary {
  lovedCount: number;
  skippedCount: number;
  missedCount: number;
  feedback: string | null;
  submittedAt: string | null;
}

export function useTripDetail(tripId: string) {
  const [trip, setTrip] = useState<ApiTrip | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [myUserId, setMyUserId] = useState<string | null>(null);
  const [hasReflected, setHasReflected] = useState(false);
  const [reflectionSummary, setReflectionSummary] = useState<ReflectionSummary | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [errorMessage, setErrorMessage] = useState("Failed to load trip");

  const fetchTrip = useCallback(async () => {
    setFetchState("loading");
    try {
      const res = await fetch(`/api/trips/${tripId}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (res.status === 404) {
          throw new Error("Trip not found");
        }
        if (res.status === 403) {
          throw new Error("You do not have access to this trip");
        }
        throw new Error(data.error || "Failed to load trip");
      }
      const { trip: tripData, myRole: role, myUserId: odId, hasReflected: reflected, reflectionSummary: refSummary } = await res.json();
      // Derive convenience fields from first leg
      const leg0 = tripData.legs?.[0];
      tripData.city = leg0?.city ?? "";
      tripData.country = leg0?.country ?? "";
      tripData.destination = leg0?.destination ?? "";
      tripData.timezone = leg0?.timezone ?? "UTC";
      setTrip(tripData);
      setMyRole(role);
      setMyUserId(odId ?? null);
      setHasReflected(reflected ?? false);
      setReflectionSummary(refSummary ?? null);
      setFetchState("success");
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load trip"
      );
      setFetchState("error");
    }
  }, [tripId]);

  useEffect(() => {
    fetchTrip();
  }, [fetchTrip]);

  return { trip, setTrip, myRole, myUserId, hasReflected, reflectionSummary, fetchState, errorMessage, fetchTrip };
}
