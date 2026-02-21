// ErrorState — Error display with optional retry.
//
// Usage:
//   <ErrorState />
//   <ErrorState message="Failed to load itinerary" onRetry={() => refetch()} />

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = "Something went wrong",
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      className="bg-error-bg border border-error/20 rounded-2xl p-6 flex flex-col items-center text-center"
      role="alert"
    >
      {/* Error icon */}
      <div
        className="w-11 h-11 rounded-xl bg-error-bg flex items-center justify-center mb-3"
        aria-hidden="true"
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-error"
        >
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </div>

      {/* Message */}
      <p className="text-error text-sm font-medium mb-4">
        {message}
      </p>

      {/* Retry button */}
      {onRetry && (
        <button
          type="button"
          className="btn-ghost"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  );
}
