"use client";

/**
 * useCardViewTracker -- attaches IntersectionObserver-based impression
 * tracking to a slot card element.
 *
 * Returns a ref callback. Attach it to the card's root element:
 *   const { ref } = useCardViewTracker({ activityNodeId, position, tripId });
 *   <article ref={ref} ...>
 *
 * Automatically emits card_impression (after 1s threshold) and card_dwell
 * (on unmount/detach) events through the ImpressionTracker singleton.
 */

import { useCallback, useRef, useEffect } from "react";
import { impressionTracker } from "@/lib/events/impressions";

interface UseCardViewTrackerOptions {
  activityNodeId: string;
  position: number;
  tripId: string;
}

export function useCardViewTracker(options: UseCardViewTrackerOptions): {
  ref: (el: HTMLElement | null) => void;
} {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Track the currently observed element so we can clean up
  const elementRef = useRef<HTMLElement | null>(null);

  // Cleanup: unobserve the current element if any
  const cleanup = useCallback(() => {
    if (elementRef.current) {
      impressionTracker.unobserve(elementRef.current);
      elementRef.current = null;
    }
  }, []);

  // Ref callback: observe new element, unobserve old one
  const ref = useCallback(
    (el: HTMLElement | null) => {
      // Detach from previous element
      cleanup();

      if (el) {
        const { activityNodeId, position, tripId } = optionsRef.current;
        impressionTracker.observe(el, {
          activityNodeId,
          position,
          tripId,
        });
        elementRef.current = el;
      }
    },
    [cleanup]
  );

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return { ref };
}
