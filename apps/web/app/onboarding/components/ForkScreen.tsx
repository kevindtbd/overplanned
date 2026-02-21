"use client";

interface ForkScreenProps {
  onPlanTrip: () => void;
  onExplore: () => void;
}

function CompassIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <polygon
        points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"
        fill="currentColor"
        stroke="none"
        opacity={0.15}
      />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

function MapIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4z" />
      <path d="M8 2v16" />
      <path d="M16 6v16" />
    </svg>
  );
}

export function ForkScreen({ onPlanTrip, onExplore }: ForkScreenProps) {
  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center px-4">
      <h1 className="font-sora text-3xl font-semibold text-primary sm:text-4xl">
        What brings you here?
      </h1>
      <p className="mt-3 max-w-md text-center text-secondary">
        Whether you have a trip in mind or just want to discover new places,
        we'll tailor the experience for you.
      </p>

      <div className="mt-10 grid w-full max-w-lg gap-4 sm:grid-cols-2">
        <button
          onClick={onPlanTrip}
          className="group card flex flex-col items-center gap-4 p-6 transition-all duration-150 hover:border-accent hover:shadow-md focus-visible:ring-2 focus-visible:ring-accent"
        >
          <CompassIcon className="h-10 w-10 text-accent transition-transform duration-150 group-hover:scale-110" />
          <div className="text-center">
            <span className="block font-sora text-lg font-semibold text-primary">
              Plan a trip
            </span>
            <span className="label-mono mt-1 block">destination + dates</span>
          </div>
        </button>

        <button
          onClick={onExplore}
          className="group card flex flex-col items-center gap-4 p-6 transition-all duration-150 hover:border-accent hover:shadow-md focus-visible:ring-2 focus-visible:ring-accent"
        >
          <MapIcon className="h-10 w-10 text-accent transition-transform duration-150 group-hover:scale-110" />
          <div className="text-center">
            <span className="block font-sora text-lg font-semibold text-primary">
              Just exploring
            </span>
            <span className="label-mono mt-1 block">browse the feed</span>
          </div>
        </button>
      </div>
    </div>
  );
}
