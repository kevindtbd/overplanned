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

export interface ApiTrip {
  id: string;
  name: string | null;
  destination: string;
  city: string;
  country: string;
  timezone: string;
  startDate: string;
  endDate: string;
  mode: string;
  status: string;
  planningProgress: number;
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
}

export type FetchState = "loading" | "error" | "success";

export function useTripDetail(tripId: string) {
  const [trip, setTrip] = useState<ApiTrip | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
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
      const { trip: tripData, myRole: role } = await res.json();
      setTrip(tripData);
      setMyRole(role);
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

  return { trip, setTrip, myRole, fetchState, errorMessage, fetchTrip };
}
