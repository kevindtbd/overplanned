'use client';

import Link from 'next/link';

interface ErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function TripError({ error, reset }: ErrorBoundaryProps) {
  return (
    <div className="min-h-screen bg-base flex items-center justify-center px-6">
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center max-w-md">
        {/* Error icon container */}
        <div
          className="w-14 h-14 rounded-2xl bg-error-bg flex items-center justify-center mb-4"
          aria-hidden="true"
        >
          <svg
            className="w-6 h-6 text-error"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        {/* Title */}
        <h3 className="font-sora italic text-xl text-ink-100 mb-2 leading-snug">
          Unable to load trip
        </h3>

        {/* Description */}
        <p className="text-ink-400 text-sm font-light leading-relaxed mb-5">
          {error.message || 'An unexpected error occurred while loading this trip.'}
        </p>

        {/* Actions */}
        <div className="flex flex-col gap-3 w-full">
          <button
            type="button"
            className="btn-primary w-full"
            onClick={reset}
          >
            Try again
          </button>

          <Link
            href="/dashboard"
            className="text-sm text-ink-400 hover:text-ink-200 transition-colors"
          >
            ← Back to dashboard
          </Link>
        </div>

        {/* Error digest for debugging */}
        {error.digest && (
          <p className="mt-6 text-xs font-dm-mono text-ink-500">
            Error ID: {error.digest}
          </p>
        )}
      </div>
    </div>
  );
}
