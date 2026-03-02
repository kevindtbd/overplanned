"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { LAUNCH_CITIES, type CityData } from "@/lib/cities";

export type { CityData };

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

interface DestinationStepProps {
  value: CityData | null;
  onChange: (city: CityData) => void;
}

export function DestinationStep({ value, onChange }: DestinationStepProps) {
  const [query, setQuery] = useState(value?.destination ?? "");
  const [isOpen, setIsOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(-1);
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return LAUNCH_CITIES;
    const q = query.toLowerCase();
    return LAUNCH_CITIES.filter(
      (c) =>
        c.city.toLowerCase().includes(q) ||
        c.state.toLowerCase().includes(q) ||
        c.destination.toLowerCase().includes(q)
    );
  }, [query]);

  useEffect(() => {
    setFocusIndex(-1);
  }, [filtered]);

  function handleSelect(city: CityData) {
    onChange(city);
    setQuery(city.destination);
    setIsOpen(false);
    setFocusIndex(-1);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!isOpen) {
      if (e.key === "ArrowDown") {
        setIsOpen(true);
        setFocusIndex(0);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      setFocusIndex((i) => Math.min(i + 1, filtered.length - 1));
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setFocusIndex((i) => Math.max(i - 1, 0));
      e.preventDefault();
    } else if (e.key === "Enter" && focusIndex >= 0) {
      handleSelect(filtered[focusIndex]);
      e.preventDefault();
    } else if (e.key === "Escape") {
      setIsOpen(false);
      setFocusIndex(-1);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        Where are you headed?
      </h2>
      <p className="label-mono mt-2">pick a city</p>

      <div className="relative mt-6">
        <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search cities..."
          className="w-full rounded-xl border-[1.5px] border-ink-700 bg-input py-3 pl-10 pr-4 font-sora text-primary placeholder:text-secondary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          role="combobox"
          aria-expanded={isOpen}
          aria-controls="city-listbox"
          aria-activedescendant={
            focusIndex >= 0 ? `city-option-${focusIndex}` : undefined
          }
          autoComplete="off"
        />

        {isOpen && filtered.length > 0 && (
          <ul
            id="city-listbox"
            ref={listRef}
            role="listbox"
            className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-ink-700 bg-surface shadow-lg"
          >
            {filtered.map((city, i) => (
              <li
                key={city.slug}
                id={`city-option-${i}`}
                role="option"
                aria-selected={value?.slug === city.slug}
                className={`cursor-pointer px-4 py-3 transition-colors ${
                  i === focusIndex
                    ? "bg-accent/10 text-primary"
                    : "text-primary hover:bg-ink-700/50"
                } ${value?.slug === city.slug ? "border-l-2 border-accent" : ""}`}
                onMouseDown={() => handleSelect(city)}
                onMouseEnter={() => setFocusIndex(i)}
              >
                <span className="font-sora font-medium">{city.city}</span>
                <span className="ml-2 font-dm-mono text-xs text-secondary">
                  {city.state || city.country}
                </span>
              </li>
            ))}
          </ul>
        )}

        {isOpen && filtered.length === 0 && query.trim() && (
          <div className="absolute z-10 mt-1 w-full rounded-lg border border-ink-700 bg-surface p-4 shadow-lg">
            <p className="text-center text-sm text-secondary">
              Not in our list? Type any city name.
            </p>
          </div>
        )}
      </div>

      {value && (
        <div className="mt-4 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
          <span className="label-mono">selected</span>
          <p className="mt-1 font-sora font-medium text-primary">
            {value.destination}
          </p>
          <p className="font-dm-mono text-xs text-secondary">{value.timezone}</p>
        </div>
      )}
    </div>
  );
}
