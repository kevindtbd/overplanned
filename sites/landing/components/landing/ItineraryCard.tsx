"use client";

import { useState } from "react";

/* ------------------------------------------------------------------ */
/*  SVG helper                                                         */
/* ------------------------------------------------------------------ */

function TruckIcon() {
  return (
    <svg
      width="9"
      height="9"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--ink-500)"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <rect x="1" y="3" width="15" height="13" rx="2" />
      <path d="M16 8h4l3 3v5h-7V8z" />
      <circle cx="5.5" cy="18.5" r="2.5" />
      <circle cx="18.5" cy="18.5" r="2.5" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Day data                                                           */
/* ------------------------------------------------------------------ */

const DAYS = ["Wed", "Thu", "Fri", "Sat", "Sun"] as const;

interface SlotData {
  name: string;
  image: string;
  note: string;
  tags: { label: string; class: string }[];
  badge?: { label: string; class: string };
  active?: boolean;
}

interface TransitData {
  text: string;
}

interface DayContent {
  header: string;
  headerMeta: string;
  slots: (SlotData | TransitData)[];
}

function isSlot(item: SlotData | TransitData): item is SlotData {
  return "name" in item;
}

const DAY_DATA: Record<(typeof DAYS)[number], DayContent> = {
  Wed: {
    header: "Kyoto \u00B7 Day 1",
    headerMeta: "Wednesday \u00B7 3 Slots",
    slots: [
      {
        name: "Nishiki Market",
        image: "https://images.unsplash.com/photo-1545569341-9eb8b30979d9?w=300&q=70&auto=format&fit=crop",
        note: "morning haul before the tour groups",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Tabelog \u00B7 1.8k", class: "bg-info-bg text-info" },
        ],
        badge: { label: "Booked", class: "bg-[rgba(61,122,82,0.88)] text-white" },
      },
      { text: "12 min walk" } as TransitData,
      {
        name: "Pontocho alley stroll",
        image: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=300&q=70&auto=format&fit=crop",
        note: "lanterns come on around 17:00",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
        ],
      },
    ],
  },
  Thu: {
    header: "Kyoto \u00B7 Day 2",
    headerMeta: "Thursday \u00B7 3 Slots",
    slots: [
      {
        name: "Arashiyama bamboo",
        image: "https://images.unsplash.com/photo-1528164344705-47542687000d?w=300&q=70&auto=format&fit=crop",
        note: "arrive before 08:00 or skip it",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Busy 10-14", class: "bg-warning-bg text-warning" },
        ],
        badge: { label: "Visited", class: "bg-[rgba(61,122,82,0.88)] text-white" },
      },
      { text: "25 min bus \u00B7 \u00A5230" } as TransitData,
      {
        name: "Monkey Park Iwatayama",
        image: "https://images.unsplash.com/photo-1462275646964-a0e3c11f18a6?w=300&q=70&auto=format&fit=crop",
        note: "steep hike, views worth it",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
        ],
      },
    ],
  },
  Fri: {
    header: "Kyoto \u00B7 Day 3",
    headerMeta: "Friday \u00B7 4 Slots",
    slots: [
      {
        name: "Fushimi Inari",
        image: "https://images.unsplash.com/photo-1478436127897-769e1b3f0f36?w=300&q=70&auto=format&fit=crop",
        note: "left before the crowds hit",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Tabelog \u00B7 2.1k", class: "bg-info-bg text-info" },
        ],
        badge: { label: "Visited", class: "bg-[rgba(61,122,82,0.88)] text-white" },
      },
      { text: "18 min taxi \u00B7 \u00A51,200" } as TransitData,
      {
        name: "Kinkaku-ji",
        image: "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=300&q=70&auto=format&fit=crop",
        note: "weekday afternoon \u00B7 thins out by 15:00",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Tabelog \u00B7 4.2k", class: "bg-info-bg text-info" },
          { label: "Busy 10-14", class: "bg-warning-bg text-warning" },
        ],
        badge: { label: "Booked", class: "bg-[rgba(61,122,82,0.88)] text-white" },
        active: true,
      },
      {
        name: "Pontocho izakaya",
        image: "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=300&q=70&auto=format&fit=crop",
        note: "locals-only counter \u00B7 full by 20:00",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Tabelog \u00B7 3.8k", class: "bg-info-bg text-info" },
        ],
        badge: { label: "Book Now", class: "bg-[rgba(26,22,18,0.6)] text-white/[0.92]" },
      },
    ],
  },
  Sat: {
    header: "Kyoto \u00B7 Day 4",
    headerMeta: "Saturday \u00B7 3 Slots",
    slots: [
      {
        name: "Philosopher's Path",
        image: "https://images.unsplash.com/photo-1524413840807-0c3cb6fa808d?w=300&q=70&auto=format&fit=crop",
        note: "cherry blossom corridor at dawn",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
        ],
      },
      { text: "15 min walk" } as TransitData,
      {
        name: "Gion district",
        image: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=300&q=70&auto=format&fit=crop",
        note: "evening stroll \u00B7 geisha spotting is luck",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Tabelog \u00B7 900", class: "bg-info-bg text-info" },
        ],
      },
    ],
  },
  Sun: {
    header: "Kyoto \u00B7 Day 5",
    headerMeta: "Sunday \u00B7 2 Slots",
    slots: [
      {
        name: "Toji Temple flea market",
        image: "https://images.unsplash.com/photo-1545569341-9eb8b30979d9?w=300&q=70&auto=format&fit=crop",
        note: "first Sunday of the month only",
        tags: [
          { label: "Local", class: "bg-success-bg text-success" },
          { label: "Monthly", class: "bg-warning-bg text-warning" },
        ],
      },
      { text: "22 min train \u00B7 \u00A5280" } as TransitData,
      {
        name: "Departure prep",
        image: "https://images.unsplash.com/photo-1528164344705-47542687000d?w=300&q=70&auto=format&fit=crop",
        note: "pack up, coin locker near station",
        tags: [],
      },
    ],
  },
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ItineraryCard() {
  const [activeDay, setActiveDay] = useState<(typeof DAYS)[number]>("Fri");
  const day = DAY_DATA[activeDay];

  return (
    <div className="card overflow-hidden shadow-xl rounded-[20px]">
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-[14px] border-b border-ink-700">
        <span className="font-sora text-[15px] font-semibold tracking-[-0.02em] text-ink-100">
          {day.header}
        </span>
        <span className="font-dm-mono text-[8px] text-ink-500 tracking-[0.08em] uppercase">
          {day.headerMeta}
        </span>
      </div>
      {/* Day tabs */}
      <div className="flex px-[18px] border-b border-ink-700 overflow-hidden">
        {DAYS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setActiveDay(d)}
            className={`py-2 px-2.5 font-dm-mono text-[8px] tracking-[0.08em] uppercase cursor-pointer whitespace-nowrap border-b-2 transition-colors bg-transparent ${
              d === activeDay
                ? "text-ink-100 border-accent"
                : "text-ink-500 border-transparent hover:text-ink-300"
            }`}
          >
            {d}
          </button>
        ))}
      </div>
      {/* Slots */}
      {day.slots.map((item, i) =>
        isSlot(item) ? (
          <div
            key={`${activeDay}-${i}`}
            className={`flex items-stretch border-b border-ink-700 last:border-b-0 ${
              item.active
                ? "bg-accent-light border-l-[3px] border-l-accent cursor-pointer"
                : "hover:bg-warm transition-colors cursor-pointer"
            }`}
          >
            <div className="w-[72px] h-[72px] flex-shrink-0 overflow-hidden relative">
              <img
                src={item.image}
                alt={item.name}
                className="w-full h-full object-cover block hover:scale-[1.06] transition-transform duration-400"
              />
              {item.badge && (
                <span className={`absolute bottom-1 left-1 font-dm-mono text-[7px] tracking-[0.04em] uppercase px-[5px] py-[1px] rounded-full ${item.badge.class}`}>
                  {item.badge.label}
                </span>
              )}
            </div>
            <div className="flex-1 px-3.5 py-2.5 flex flex-col justify-center">
              <span className="text-[13px] font-medium text-ink-100 mb-0.5">
                {item.name}
              </span>
              <span className="text-[11px] text-ink-400 font-light italic mb-1">
                {item.note}
              </span>
              {item.tags.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {item.tags.map((tag) => (
                    <span
                      key={tag.label}
                      className={`font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full ${tag.class}`}
                    >
                      {tag.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div
            key={`transit-${activeDay}-${i}`}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-raised border-b border-ink-700"
          >
            <TruckIcon />
            <span className="font-dm-mono text-[9px] text-ink-500">
              {item.text}
            </span>
          </div>
        ),
      )}
    </div>
  );
}
