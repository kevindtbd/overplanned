"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ForkScreen } from "./components/ForkScreen";
import {
  DestinationStep,
  type LaunchCity,
} from "./components/DestinationStep";
import { DatesStep } from "./components/DatesStep";
import { TripDNAStep, type Pace, type MorningPreference } from "./components/TripDNAStep";
import { TemplateStep } from "./components/TemplateStep";

type WizardStep = "fork" | "destination" | "dates" | "name" | "dna" | "template";

const STEP_ORDER: WizardStep[] = [
  "fork",
  "destination",
  "dates",
  "name",
  "dna",
  "template",
];

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

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>("fork");
  const [isSubmitting, setIsSubmitting] = useState(false);

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
  const [template, setTemplate] = useState<string | null>(null);

  const stepIndex = STEP_ORDER.indexOf(step);
  const totalSteps = STEP_ORDER.length - 1; // exclude fork from progress
  const progressStep = stepIndex > 0 ? stepIndex : 0;

  function canAdvance(): boolean {
    switch (step) {
      case "fork":
        return true;
      case "destination":
        return destination !== null;
      case "dates":
        return !!startDate && !!endDate && endDate >= startDate;
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

    try {
      const payload = {
        destination: destination.destination,
        city: destination.city,
        country: destination.country,
        timezone: destination.timezone,
        startDate: new Date(startDate).toISOString(),
        endDate: new Date(endDate).toISOString(),
        name: tripName.trim(),
        mode: "solo" as const,
        status: "planning" as const,
        presetTemplate: template,
        personaSeed: {
          pace,
          morningPreference,
          foodPreferences,
          template,
        },
      };

      const res = await fetch("/api/trips", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error("Failed to create trip");
      }

      const { tripId } = await res.json();
      router.push(`/trips/${tripId}/generating`);
    } catch {
      // TODO: surface error to user via toast
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-base">
      {/* Progress bar — hidden on fork screen */}
      {step !== "fork" && (
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
                  className="h-full rounded-full bg-accenttransition-all duration-300"
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
        </div>
      )}

      {/* Step content */}
      <div className={step !== "fork" ? "px-4 pb-28 pt-16" : ""}>
        {step === "fork" && (
          <ForkScreen
            onPlanTrip={() => setStep("destination")}
            onExplore={() => router.push("/discover")}
          />
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
              className="mt-6 w-full rounded-lg border border-ink-700 bg-surface py-3 px-4 font-sora text-primary placeholder:text-secondary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
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
              onPaceChange={setPace}
              onMorningChange={setMorningPreference}
              onFoodToggle={handleFoodToggle}
            />
          </div>
        )}

        {step === "template" && (
          <div className="pt-8">
            <TemplateStep selected={template} onSelect={setTemplate} />
          </div>
        )}
      </div>

      {/* Bottom navigation — hidden on fork screen */}
      {step !== "fork" && (
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
