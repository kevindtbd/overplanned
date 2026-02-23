"use client";

import { useState, useCallback, useRef, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ForkScreen } from "./components/ForkScreen";
import { BackfillStep } from "./components/BackfillStep";
import {
  DestinationStep,
  LAUNCH_CITIES,
  type LaunchCity,
} from "./components/DestinationStep";
import { DatesStep } from "./components/DatesStep";
import { TripDNAStep, type Pace, type MorningPreference } from "./components/TripDNAStep";
import { TemplateStep } from "./components/TemplateStep";
import { ErrorState } from "@/components/states";
import { nightsBetween } from "@/lib/utils/dates";
import { MAX_TRIP_NIGHTS } from "@/lib/constants/trip";

type WizardStep = "fork" | "backfill" | "destination" | "dates" | "name" | "dna" | "template";

const STEP_ORDER: WizardStep[] = [
  "fork",
  "backfill",
  "destination",
  "dates",
  "name",
  "dna",
  "template",
];

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function generateTripName(city: string, startDate: string): string {
  if (!startDate) return `${city} trip`;
  const d = new Date(startDate);
  const month = d.toLocaleString("en-US", { month: "short" });
  const year = d.getFullYear();
  return `${city} ${month} ${year}`;
}

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function LoadingSpinner({ className }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className ?? ""}`}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        opacity={0.25}
      />
      <path
        d="M12 2a10 10 0 019.95 9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function OnboardingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState<WizardStep>("fork");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [draftSaveError, setDraftSaveError] = useState(false);

  // Form state
  const [destination, setDestination] = useState<LaunchCity | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [tripName, setTripName] = useState("");
  const [tripNameTouched, setTripNameTouched] = useState(false);
  const [pace, setPace] = useState<Pace | null>(null);
  const [morningPreference, setMorningPreference] =
    useState<MorningPreference | null>(null);
  const [foodPreferences, setFoodPreferences] = useState<string[]>([]);
  const [freeformVibes, setFreeformVibes] = useState("");
  const [template, setTemplate] = useState<string | null>(null);

  // Draft state refs
  const isDraftSaving = useRef(false);
  const draftIdRef = useRef<string | null>(null);

  // Quick-start pre-fill from query params (e.g. /onboarding?city=Tokyo&step=dates)
  // SECURITY: Only use values from the matched LAUNCH_CITIES entry.
  // Never use raw query param values directly.
  const didPrefill = useRef(false);
  useEffect(() => {
    if (didPrefill.current) return;
    const startStep = searchParams.get("step");

    // Direct jump to backfill step (from dashboard "Add a past trip")
    if (startStep === "backfill") {
      didPrefill.current = true;
      setStep("backfill");
      router.replace("/onboarding", { scroll: false });
      return;
    }

    const prefilledCity = searchParams.get("city");
    if (!prefilledCity || startStep !== "dates") return;

    const matchedDest = LAUNCH_CITIES.find(
      (d) => d.city.toLowerCase() === prefilledCity.toLowerCase()
    );
    if (matchedDest) {
      didPrefill.current = true;
      setDestination(matchedDest);
      setStep("dates");
      router.replace("/onboarding", { scroll: false });
    }
  }, [searchParams, router]);

  // Resume flow from query params (e.g. /onboarding?resume=<tripId>)
  const didResume = useRef(false);
  useEffect(() => {
    if (didResume.current) return;
    const resumeId = searchParams.get("resume");
    if (!resumeId) return;

    // Validate UUID format before hitting API
    if (!UUID_RE.test(resumeId)) {
      router.replace("/onboarding", { scroll: false });
      return;
    }

    didResume.current = true;

    fetch(`/api/trips/${resumeId}`)
      .then(async (res) => {
        if (!res.ok) {
          router.replace("/onboarding", { scroll: false });
          return;
        }
        const data = await res.json();
        const trip = data.trip;

        // If trip is not a draft, redirect to the trip detail page
        if (trip.status !== "draft") {
          router.replace(`/trip/${resumeId}`);
          return;
        }

        // Pre-fill destination from LAUNCH_CITIES match
        const matchedDest = LAUNCH_CITIES.find(
          (d) => d.city.toLowerCase() === (trip.city ?? "").toLowerCase()
        );
        if (matchedDest) {
          setDestination(matchedDest);
        }

        // Convert ISO dates to YYYY-MM-DD for the DatesStep inputs
        if (trip.startDate) {
          setStartDate(new Date(trip.startDate).toISOString().split("T")[0]);
        }
        if (trip.endDate) {
          setEndDate(new Date(trip.endDate).toISOString().split("T")[0]);
        }

        // Store draft ID and jump to name step
        draftIdRef.current = resumeId;
        setStep("name");
        router.replace("/onboarding", { scroll: false });
      })
      .catch(() => {
        router.replace("/onboarding", { scroll: false });
      });
  }, [searchParams, router]);

  const stepIndex = STEP_ORDER.indexOf(step);
  const totalSteps = STEP_ORDER.length - 1; // exclude fork from progress
  const progressStep = stepIndex > 0 ? stepIndex : 0;

  function canAdvance(): boolean {
    switch (step) {
      case "fork":
        return true;
      case "backfill":
        return true; // handled by its own skip/continue buttons
      case "destination":
        return destination !== null;
      case "dates":
        return (
          !!startDate &&
          !!endDate &&
          endDate > startDate &&
          nightsBetween(startDate, endDate) <= MAX_TRIP_NIGHTS
        );
      case "name":
        return tripName.trim().length > 0;
      case "dna":
        return pace !== null && morningPreference !== null;
      case "template":
        return true; // optional
      default:
        return false;
    }
  }

  function goNext() {
    const idx = STEP_ORDER.indexOf(step);
    if (idx < STEP_ORDER.length - 1) {
      const nextStep = STEP_ORDER[idx + 1];

      // Auto-generate trip name when entering name step
      if (nextStep === "name" && !tripNameTouched && destination) {
        setTripName(generateTripName(destination.city, startDate));
      }

      // Fire-and-forget draft save when advancing from dates step
      if (step === "dates" && canAdvance()) {
        if (!isDraftSaving.current && !draftIdRef.current && destination) {
          isDraftSaving.current = true;
          setDraftSaveError(false);

          fetch("/api/trips/draft", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              destination: destination.destination,
              city: destination.city,
              country: destination.country,
              timezone: destination.timezone,
              startDate: new Date(startDate).toISOString(),
              endDate: new Date(endDate).toISOString(),
            }),
          })
            .then(async (res) => {
              if (res.ok) {
                const data = await res.json();
                draftIdRef.current = data.trip.id;
              } else {
                console.error("[onboarding] Draft save failed:", res.status);
                setDraftSaveError(true);
              }
            })
            .catch((err) => {
              console.error("[onboarding] Draft save error:", err);
              setDraftSaveError(true);
            })
            .finally(() => {
              isDraftSaving.current = false;
            });
        }
      }

      // Step transition is NOT blocked by the draft save — fire and forget
      setStep(nextStep);
    }
  }

  function goBack() {
    const idx = STEP_ORDER.indexOf(step);
    if (idx > 0) {
      setStep(STEP_ORDER[idx - 1]);
    }
  }

  const handleFoodToggle = useCallback((chip: string) => {
    setFoodPreferences((prev) =>
      prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip]
    );
  }, []);

  async function handleComplete() {
    if (!destination || !startDate || !endDate || !pace || !morningPreference) {
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      let trip: { id: string };

      if (draftIdRef.current) {
        // Promote the existing draft via PATCH
        const patchPayload = {
          name: tripName.trim(),
          presetTemplate: template,
          personaSeed: {
            pace,
            morningPreference,
            foodPreferences,
            freeformVibes: freeformVibes.trim() || undefined,
            template,
          },
          status: "planning" as const,
          mode: "solo" as const,
        };

        const res = await fetch(`/api/trips/${draftIdRef.current}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patchPayload),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error || "Failed to create trip");
        }

        const { trip: patchedTrip } = await res.json();
        trip = patchedTrip;
      } else {
        // No draft — fall back to full POST
        const payload = {
          destination: destination.destination,
          city: destination.city,
          country: destination.country,
          timezone: destination.timezone,
          startDate: new Date(startDate).toISOString(),
          endDate: new Date(endDate).toISOString(),
          name: tripName.trim(),
          mode: "solo" as const,
          presetTemplate: template,
          personaSeed: {
            pace,
            morningPreference,
            foodPreferences,
            freeformVibes: freeformVibes.trim() || undefined,
            template,
          },
        };

        const res = await fetch("/api/trips", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error || "Failed to create trip");
        }

        const { trip: createdTrip } = await res.json();
        trip = createdTrip;
      }

      sessionStorage.setItem(`new-trip-${trip.id}`, "1");
      router.push(`/trip/${trip.id}`);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Something went wrong. Please try again."
      );
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-base">
      {/* Progress bar -- hidden on fork and backfill screens */}
      {step !== "fork" && step !== "backfill" && (
        <div className="fixed left-0 right-0 top-0 z-20 bg-base/80 backdrop-blur-sm">
          <div className="mx-auto flex max-w-lg items-center gap-3 px-4 py-3">
            <button
              onClick={goBack}
              className="flex h-8 w-8 items-center justify-center rounded-full text-secondary transition-colors hover:bg-surface hover:text-primary"
              aria-label="Go back"
            >
              <ArrowLeftIcon className="h-4 w-4" />
            </button>
            <div className="flex-1">
              <div className="h-1 overflow-hidden rounded-full bg-ink-700">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-300"
                  style={{
                    width: `${(progressStep / totalSteps) * 100}%`,
                  }}
                />
              </div>
            </div>
            <span className="label-mono min-w-[3rem] text-right">
              {progressStep}/{totalSteps}
            </span>
          </div>
          {/* Non-blocking draft save error */}
          {draftSaveError && (
            <div
              data-testid="draft-save-error"
              className="mx-auto max-w-lg px-4 pb-2 font-dm-mono text-xs text-secondary"
            >
              Could not save your progress yet. Your trip will still be created at the end.
            </div>
          )}
        </div>
      )}

      {/* Step content */}
      <div className={step !== "fork" && step !== "backfill" ? "px-4 pb-28 pt-16" : step === "backfill" ? "px-4" : ""}>
        {step === "fork" && (
          <ForkScreen
            onPlanTrip={() => setStep("backfill")}
            onExplore={() => router.push("/discover")}
          />
        )}

        {step === "backfill" && (
          <div className="pt-8">
            <BackfillStep
              onSkip={() => setStep("destination")}
              onContinue={() => setStep("destination")}
            />
          </div>
        )}

        {step === "destination" && (
          <div className="pt-8">
            <DestinationStep value={destination} onChange={setDestination} />
          </div>
        )}

        {step === "dates" && (
          <div className="pt-8">
            <DatesStep
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={setStartDate}
              onEndDateChange={setEndDate}
            />
          </div>
        )}

        {step === "name" && (
          <div className="mx-auto w-full max-w-md pt-8">
            <h2 className="font-sora text-2xl font-semibold text-primary">
              Name your trip
            </h2>
            <p className="label-mono mt-2">you can change this anytime</p>
            <input
              type="text"
              value={tripName}
              onChange={(e) => {
                setTripName(e.target.value);
                setTripNameTouched(true);
              }}
              placeholder="e.g. Tokyo Golden Week"
              maxLength={80}
              className="mt-6 w-full rounded-xl border-[1.5px] border-ink-700 bg-input py-3 px-4 font-sora text-primary placeholder:text-secondary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
            <p className="mt-2 text-right font-dm-mono text-xs text-secondary">
              {tripName.length}/80
            </p>
          </div>
        )}

        {step === "dna" && (
          <div className="pt-8">
            <TripDNAStep
              pace={pace}
              morningPreference={morningPreference}
              foodPreferences={foodPreferences}
              freeformVibes={freeformVibes}
              onPaceChange={setPace}
              onMorningChange={setMorningPreference}
              onFoodToggle={handleFoodToggle}
              onFreeformChange={setFreeformVibes}
            />
          </div>
        )}

        {step === "template" && (
          <div className="pt-8">
            <TemplateStep selected={template} onSelect={setTemplate} />
          </div>
        )}
      </div>

      {/* Submission error */}
      {submitError && step === "template" && (
        <div className="fixed bottom-24 left-0 right-0 z-30 px-4">
          <div className="mx-auto max-w-lg">
            <ErrorState
              message={submitError}
              onRetry={() => {
                setSubmitError(null);
                handleComplete();
              }}
            />
          </div>
        </div>
      )}

      {/* Bottom navigation -- hidden on fork and backfill screens (backfill has its own buttons) */}
      {step !== "fork" && step !== "backfill" && (
        <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-ink-700 bg-base/90 backdrop-blur-sm">
          <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-4">
            {step === "template" ? (
              <>
                <button
                  onClick={() => handleComplete()}
                  disabled={isSubmitting}
                  className="label-mono text-secondary hover:text-primary"
                >
                  Skip template
                </button>
                <button
                  onClick={() => handleComplete()}
                  disabled={isSubmitting}
                  className="btn-primary flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <LoadingSpinner className="h-4 w-4" />
                  ) : (
                    <CheckIcon className="h-4 w-4" />
                  )}
                  <span>Create trip</span>
                </button>
              </>
            ) : (
              <>
                <div />
                <button
                  onClick={goNext}
                  disabled={!canAdvance()}
                  className="btn-primary flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span>Continue</span>
                  <ArrowRightIcon className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-base" />}>
      <OnboardingContent />
    </Suspense>
  );
}
