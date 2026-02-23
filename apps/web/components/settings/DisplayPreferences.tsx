"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------- Types ----------

type DisplayState = {
  distance: "mi" | "km";
  temperature: "F" | "C";
  dateFormat: "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD";
  timeFormat: "12h" | "24h";
  theme: "light" | "dark" | "system";
};

const DEFAULTS: DisplayState = {
  distance: "mi",
  temperature: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

// ---------- Field Definitions ----------

type FieldDef<K extends keyof DisplayState> = {
  key: K;
  legend: string;
  options: { value: DisplayState[K]; label: string }[];
  dmMono?: boolean;
};

const FIELDS: FieldDef<keyof DisplayState>[] = [
  {
    key: "distance",
    legend: "Distance",
    options: [
      { value: "mi", label: "mi" },
      { value: "km", label: "km" },
    ],
  },
  {
    key: "temperature",
    legend: "Temperature",
    options: [
      { value: "F", label: "F" },
      { value: "C", label: "C" },
    ],
  },
  {
    key: "dateFormat",
    legend: "Date format",
    dmMono: true,
    options: [
      { value: "MM/DD/YYYY", label: "MM/DD/YYYY" },
      { value: "DD/MM/YYYY", label: "DD/MM/YYYY" },
      { value: "YYYY-MM-DD", label: "YYYY-MM-DD" },
    ],
  },
  {
    key: "timeFormat",
    legend: "Time format",
    options: [
      { value: "12h", label: "12h" },
      { value: "24h", label: "24h" },
    ],
  },
  {
    key: "theme",
    legend: "Theme",
    options: [
      { value: "light", label: "Light" },
      { value: "dark", label: "Dark" },
      { value: "system", label: "System" },
    ],
  },
];

// ---------- Theme helper ----------

function applyTheme(value: string) {
  if (value === "system") {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    localStorage.removeItem("theme");
  } else {
    document.documentElement.setAttribute("data-theme", value);
    document.documentElement.style.colorScheme = value;
    localStorage.setItem("theme", value);
  }
}

// ---------- Component ----------

export function DisplayPreferences() {
  const [prefs, setPrefs] = useState<DisplayState>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const lastSavedRef = useRef<DisplayState>(DEFAULTS);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/settings/display");
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) {
          const merged = { ...DEFAULTS, ...data };
          setPrefs(merged);
          lastSavedRef.current = merged;
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleChange = useCallback(
    <K extends keyof DisplayState>(field: K, value: DisplayState[K]) => {
      // Optimistic update
      setPrefs((prev) => {
        const next = { ...prev, [field]: value };

        // Apply theme to DOM immediately
        if (field === "theme") {
          applyTheme(value as string);
        }

        // Fire PATCH (no debounce — discrete selections)
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        fetch("/api/settings/display", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [field]: value }),
          signal: controller.signal,
        })
          .then((res) => {
            if (!res.ok) throw new Error();
            lastSavedRef.current = next;
          })
          .catch((err) => {
            if (err instanceof DOMException && err.name === "AbortError") return;
            // Revert on failure
            setPrefs(lastSavedRef.current);
            if (field === "theme") {
              applyTheme(lastSavedRef.current.theme);
            }
          });

        return next;
      });
    },
    [],
  );

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return (
    <section id="display" aria-labelledby="display-heading">
      <h2 id="display-heading" className="font-sora text-lg font-medium text-ink-100 mb-4">
        Display Preferences
      </h2>

      <div className="rounded-[20px] border border-warm-border bg-warm-surface p-5 space-y-5">
        {loading ? (
          <div className="space-y-4 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i}>
                <div className="h-3 w-20 bg-warm-border rounded mb-2" />
                <div className="flex gap-2">
                  {[1, 2].map((j) => (
                    <div key={j} className="h-8 w-16 bg-warm-border rounded-lg" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <p className="font-sora text-sm text-red-400">Failed to load display preferences.</p>
        ) : (
          <>
            {FIELDS.map((field) => {
              const useDmMono = !!field.dmMono;
              return (
                <fieldset key={field.key}>
                  <legend className="font-dm-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 mb-2">
                    {field.legend}
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {field.options.map((opt) => {
                      const selected = prefs[field.key] === opt.value;
                      return (
                        <label
                          key={opt.value}
                          className={`
                            flex items-center px-3 py-1.5 rounded-lg border cursor-pointer
                            transition-colors
                            ${useDmMono ? "font-dm-mono text-xs" : "font-sora text-sm"}
                            ${selected
                              ? "border-accent bg-accent/10 text-ink-100"
                              : "border-warm-border bg-transparent text-ink-300 hover:border-ink-400"
                            }
                          `}
                        >
                          <input
                            type="radio"
                            name={field.key}
                            value={opt.value}
                            checked={selected}
                            onChange={() => handleChange(field.key, opt.value as DisplayState[typeof field.key])}
                            className="sr-only"
                          />
                          {opt.label}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              );
            })}
          </>
        )}
      </div>
    </section>
  );
}
