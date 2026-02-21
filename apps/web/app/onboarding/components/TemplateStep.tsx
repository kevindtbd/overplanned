"use client";

interface Template {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
}

function UtensilsIcon() {
  return (
    <svg
      className="h-8 w-8"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 002-2V2" />
      <path d="M7 2v20" />
      <path d="M21 15V2v0a5 5 0 00-5 5v6c0 1.1.9 2 2 2h3zm0 0v7" />
    </svg>
  );
}

function LandmarkIcon() {
  return (
    <svg
      className="h-8 w-8"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="3" y1="22" x2="21" y2="22" />
      <line x1="6" y1="18" x2="6" y2="11" />
      <line x1="10" y1="18" x2="10" y2="11" />
      <line x1="14" y1="18" x2="14" y2="11" />
      <line x1="18" y1="18" x2="18" y2="11" />
      <polygon points="12 2 20 8 4 8" />
      <line x1="2" y1="18" x2="22" y2="18" />
    </svg>
  );
}

function MountainIcon() {
  return (
    <svg
      className="h-8 w-8"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 3l4 8 5-5 5 15H2L8 3z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      className="h-8 w-8"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

const TEMPLATES: Template[] = [
  {
    id: "foodie-weekend",
    name: "Foodie Weekend",
    description: "Restaurant-first itinerary with local gems and market crawls",
    icon: <UtensilsIcon />,
  },
  {
    id: "culture-deep-dive",
    name: "Culture Deep Dive",
    description: "Museums, temples, historic neighborhoods, and local arts",
    icon: <LandmarkIcon />,
  },
  {
    id: "adventure",
    name: "Adventure",
    description: "Outdoor activities, day trips, and off-the-beaten-path spots",
    icon: <MountainIcon />,
  },
  {
    id: "chill",
    name: "Chill",
    description: "Cafes, parks, slow walks, and zero stress",
    icon: <SunIcon />,
  },
];

interface TemplateStepProps {
  selected: string | null;
  onSelect: (templateId: string | null) => void;
}

export function TemplateStep({ selected, onSelect }: TemplateStepProps) {
  return (
    <div className="mx-auto w-full max-w-lg">
      <h2 className="font-sora text-2xl font-semibold text-primary">
        Start from a template?
      </h2>
      <p className="label-mono mt-2">optional — skip if you want full control</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {TEMPLATES.map((tpl) => (
          <button
            key={tpl.id}
            onClick={() =>
              onSelect(selected === tpl.id ? null : tpl.id)
            }
            className={`group rounded-xl border p-5 text-left transition-all duration-150 ${
              selected === tpl.id
                ? "border-accent bg-accent-light text-accent-fg"
                : "border-ink-700 bg-raised text-ink-300 hover:border-accent/50 hover:shadow-sm"
            }`}
          >
            <div
              className={`transition-colors ${
                selected === tpl.id
                  ? "text-accent"
                  : "text-secondary group-hover:text-accent"
              }`}
            >
              {tpl.icon}
            </div>
            <span className="mt-3 block font-sora text-sm font-semibold text-primary">
              {tpl.name}
            </span>
            <span className="mt-1 block font-dm-mono text-xs text-secondary">
              {tpl.description}
            </span>
          </button>
        ))}
      </div>

      {selected && (
        <button
          onClick={() => onSelect(null)}
          className="mt-4 font-dm-mono text-xs text-secondary underline underline-offset-2 hover:text-primary"
        >
          Clear selection
        </button>
      )}
    </div>
  );
}
