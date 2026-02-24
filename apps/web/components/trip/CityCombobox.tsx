"use client";

import { useState, useMemo, useRef, useEffect, useCallback } from "react";

export interface CityData {
  city: string;
  country: string;
  timezone: string;
  destination: string;
}

export const LAUNCH_CITIES: CityData[] = [
  { city: "Tokyo", country: "Japan", timezone: "Asia/Tokyo", destination: "Tokyo, Japan" },
  { city: "Kyoto", country: "Japan", timezone: "Asia/Tokyo", destination: "Kyoto, Japan" },
  { city: "Osaka", country: "Japan", timezone: "Asia/Tokyo", destination: "Osaka, Japan" },
  { city: "Bangkok", country: "Thailand", timezone: "Asia/Bangkok", destination: "Bangkok, Thailand" },
  { city: "Seoul", country: "South Korea", timezone: "Asia/Seoul", destination: "Seoul, South Korea" },
  { city: "Taipei", country: "Taiwan", timezone: "Asia/Taipei", destination: "Taipei, Taiwan" },
  { city: "Lisbon", country: "Portugal", timezone: "Europe/Lisbon", destination: "Lisbon, Portugal" },
  { city: "Barcelona", country: "Spain", timezone: "Europe/Madrid", destination: "Barcelona, Spain" },
  { city: "Mexico City", country: "Mexico", timezone: "America/Mexico_City", destination: "Mexico City, Mexico" },
  { city: "New York", country: "United States", timezone: "America/New_York", destination: "New York, United States" },
  { city: "London", country: "United Kingdom", timezone: "Europe/London", destination: "London, United Kingdom" },
  { city: "Paris", country: "France", timezone: "Europe/Paris", destination: "Paris, France" },
  { city: "Berlin", country: "Germany", timezone: "Europe/Berlin", destination: "Berlin, Germany" },
];

function SearchIcon({ className }: { className?: string }) {
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
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

interface CityComboboxProps {
  value: CityData | null;
  onChange: (city: CityData) => void;
  placeholder?: string;
  label?: string;
  id?: string;
}

export function CityCombobox({
  value,
  onChange,
  placeholder = "Search cities...",
  label,
  id = "city-combobox",
}: CityComboboxProps) {
  const [query, setQuery] = useState(value?.destination ?? "");
  const [isOpen, setIsOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(-1);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return LAUNCH_CITIES;
    const q = query.toLowerCase();
    return LAUNCH_CITIES.filter(
      (c) =>
        c.city.toLowerCase().includes(q) ||
        c.country.toLowerCase().includes(q)
    );
  }, [query]);

  useEffect(() => {
    setFocusIndex(-1);
  }, [filtered]);

  // Sync external value changes
  useEffect(() => {
    if (value) {
      setQuery(value.destination);
    }
  }, [value]);

  const handleSelect = useCallback(
    (city: CityData) => {
      onChange(city);
      setQuery(city.destination);
      setIsOpen(false);
      setFocusIndex(-1);
      setResolveError(null);
    },
    [onChange]
  );

  const resolveFreeformCity = useCallback(
    async (cityName: string) => {
      if (!cityName.trim()) return;

      // Check LAUNCH_CITIES first (client-side shortcut)
      const match = LAUNCH_CITIES.find(
        (c) => c.city.toLowerCase() === cityName.trim().toLowerCase()
      );
      if (match) {
        handleSelect(match);
        return;
      }

      setResolving(true);
      setResolveError(null);

      try {
        const res = await fetch("/api/cities/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ city: cityName.trim() }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          if (res.status === 429) {
            setResolveError("Too many city lookups. Try again later.");
          } else {
            setResolveError(data.error || "Could not resolve city");
          }
          return;
        }

        const resolved: CityData = await res.json();
        handleSelect(resolved);
      } catch {
        setResolveError("Network error resolving city");
      } finally {
        setResolving(false);
      }
    },
    [handleSelect]
  );

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!isOpen) {
      if (e.key === "ArrowDown") {
        setIsOpen(true);
        setFocusIndex(0);
        e.preventDefault();
      }
      if (e.key === "Enter" && query.trim() && filtered.length === 0) {
        resolveFreeformCity(query);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      setFocusIndex((i) => Math.min(i + 1, filtered.length));
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setFocusIndex((i) => Math.max(i - 1, 0));
      e.preventDefault();
    } else if (e.key === "Enter") {
      if (focusIndex >= 0 && focusIndex < filtered.length) {
        handleSelect(filtered[focusIndex]);
      } else if (query.trim()) {
        // Freeform resolve
        resolveFreeformCity(query);
      }
      e.preventDefault();
    } else if (e.key === "Escape") {
      setIsOpen(false);
      setFocusIndex(-1);
    }
  }

  function handleBlur() {
    // Delay to allow click events on list items
    setTimeout(() => {
      setIsOpen(false);

      // Auto-resolve freeform on blur if no value selected and query doesn't match
      if (query.trim() && (!value || value.destination !== query)) {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
          resolveFreeformCity(query);
        }, 300);
      }
    }, 200);
  }

  const showFreeformOption =
    isOpen &&
    query.trim().length >= 2 &&
    filtered.length === 0;

  return (
    <div className="relative">
      {label && (
        <label
          htmlFor={id}
          className="font-dm-mono text-xs text-ink-400 uppercase tracking-wider mb-1.5 block"
        >
          {label}
        </label>
      )}
      <div className="relative">
        <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input
          ref={inputRef}
          id={id}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            setResolveError(null);
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={resolving}
          className="w-full rounded-lg border border-ink-700 bg-base py-2.5 pl-10 pr-4 font-sora text-sm text-ink-100 placeholder:text-ink-600 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-60 transition-colors"
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={`${id}-listbox`}
          aria-activedescendant={
            focusIndex >= 0 ? `${id}-option-${focusIndex}` : undefined
          }
          autoComplete="off"
        />
        {resolving && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <svg
              className="h-4 w-4 animate-spin text-ink-400"
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
          </div>
        )}
      </div>

      {isOpen && filtered.length > 0 && (
        <ul
          id={`${id}-listbox`}
          ref={listRef}
          role="listbox"
          className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-ink-700 bg-surface shadow-lg"
        >
          {filtered.map((city, i) => (
            <li
              key={city.city}
              id={`${id}-option-${i}`}
              role="option"
              aria-selected={value?.city === city.city}
              className={`cursor-pointer px-3 py-2.5 transition-colors ${
                i === focusIndex
                  ? "bg-accent/10 text-ink-100"
                  : "text-ink-100 hover:bg-base"
              } ${value?.city === city.city ? "border-l-2 border-accent" : ""}`}
              onMouseDown={() => handleSelect(city)}
              onMouseEnter={() => setFocusIndex(i)}
            >
              <span className="font-sora text-sm font-medium">{city.city}</span>
              <span className="ml-2 font-dm-mono text-xs text-ink-400">
                {city.country}
              </span>
            </li>
          ))}
        </ul>
      )}

      {showFreeformOption && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-ink-700 bg-surface p-3 shadow-lg">
          <button
            type="button"
            onMouseDown={() => resolveFreeformCity(query)}
            className="w-full text-left font-sora text-sm text-ink-100 hover:text-accent transition-colors"
          >
            Use &ldquo;{query.trim()}&rdquo; as custom city
          </button>
          <p className="mt-1 font-dm-mono text-xs text-ink-500">
            Press Enter or click to resolve
          </p>
        </div>
      )}

      {resolveError && (
        <p className="mt-1.5 font-dm-mono text-xs text-red-400">
          {resolveError}
        </p>
      )}
    </div>
  );
}
