import type { Metadata } from "next";
import dynamic from "next/dynamic";
import LandingNav from "@/components/landing/LandingNav";
import RevealOnScroll from "@/components/landing/RevealOnScroll";
import WaitlistForm from "@/components/landing/WaitlistForm";

const GlobeCanvas = dynamic(
  () => import("@/components/landing/GlobeCanvas"),
  { ssr: false },
);
const TripMapCanvas = dynamic(
  () => import("@/components/landing/TripMapCanvas"),
  { ssr: false },
);
const ItineraryCard = dynamic(
  () => import("@/components/landing/ItineraryCard"),
  { ssr: false },
);

export const metadata: Metadata = {
  title: "Overplanned. Travel that knows you",
  description:
    "Overplanned builds your itinerary from how you actually travel. Local sources. Real-time adaptation. A plan that changes when you do.",
};

/* ------------------------------------------------------------------ */
/*  SVG helpers — inline, no icon libraries                           */
/* ------------------------------------------------------------------ */

function ArrowRightIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M5 12h14" />
      <path d="M12 5l7 7-7 7" />
    </svg>
  );
}


/* ------------------------------------------------------------------ */
/*  Persona card                                                       */
/* ------------------------------------------------------------------ */

function PersonaCard() {
  const signals = [
    { label: "Skips hotel dining", value: 0.97, muted: false },
    { label: "Local over aggregator", value: 0.94, muted: false },
    { label: "Counter seating", value: 0.88, muted: false },
    { label: "Late lunch window", value: 0.78, muted: false },
    { label: "Michelin indifferent", value: 0.54, muted: true },
  ];

  return (
    <div className="card rounded-[20px] p-7 shadow-xl">
      <div className="font-dm-mono text-[8px] tracking-[0.14em] uppercase text-ink-500 mb-2.5">
        Detected Persona &middot; Updating
      </div>
      <div className="font-lora text-[20px] font-medium italic text-ink-100 mb-1 leading-tight">
        &ldquo;Will walk 40 minutes
        <br />
        to avoid a tourist menu&rdquo;
      </div>
      <div className="text-[12px] text-ink-400 font-light mb-5">
        Inferred across 4 trips &middot; 47 behavioral signals
      </div>
      <div className="flex flex-col gap-[9px]">
        {signals.map((s) => (
          <div key={s.label} className="flex items-center gap-2.5">
            <span className="font-dm-mono text-[9px] text-ink-400 w-[124px] flex-shrink-0 text-right">
              {s.label}
            </span>
            <div className="flex-1 h-[5px] bg-ink-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${s.muted ? "bg-ink-600" : "bg-accent"}`}
                style={{ width: `${s.value * 100}%` }}
              />
            </div>
            <span
              className={`font-dm-mono text-[9px] w-7 ${s.muted ? "text-ink-600" : "text-ink-500"}`}
            >
              {s.value.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Group trip phones                                                  */
/* ------------------------------------------------------------------ */

const AVATARS = [
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=80&q=80&auto=format&fit=crop",
  "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&q=80&auto=format&fit=crop",
  "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=80&q=80&auto=format&fit=crop",
  "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=80&q=80&auto=format&fit=crop",
];

function Pip({ src }: { src: string }) {
  return (
    <div className="w-4 h-4 rounded-full overflow-hidden border-[1.5px] border-surface -ml-1 first:ml-0">
      <img src={src} alt="" className="w-full h-full object-cover block" />
    </div>
  );
}

function GroupPhones() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Agreed */}
      <div className="flex flex-col gap-1.5">
        <span className="font-dm-mono text-[8px] tracking-[0.12em] uppercase text-ink-500 text-center">
          Agreed
        </span>
        <div className="card rounded-[14px] overflow-hidden shadow-md">
          <div className="px-3 py-2 border-b border-ink-700 text-[11px] font-medium text-ink-100">
            Nishiki Market
          </div>
          <div className="p-2.5">
            <div className="flex items-center gap-1.5">
              <div className="flex">
                {AVATARS.map((a) => (
                  <Pip key={a} src={a} />
                ))}
              </div>
              <span className="font-dm-mono text-[8px] tracking-[0.06em] uppercase text-success">
                Everyone in
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Conflict */}
      <div className="flex flex-col gap-1.5">
        <span className="font-dm-mono text-[8px] tracking-[0.12em] uppercase text-ink-500 text-center">
          Conflict
        </span>
        <div className="card rounded-[14px] overflow-hidden shadow-md">
          <div className="px-3 py-2 border-b border-ink-700 text-[11px] font-medium text-ink-100">
            Kinkaku-ji
          </div>
          <div className="p-2.5">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-[3px]">
                <div className="flex">
                  <Pip src={AVATARS[0]} />
                  <Pip src={AVATARS[3]} />
                </div>
                <span className="font-dm-mono text-[8px] text-success">
                  want it
                </span>
              </div>
              <span className="font-dm-mono text-[8px] text-ink-500">vs</span>
              <div className="flex items-center gap-[3px]">
                <div className="flex">
                  <Pip src={AVATARS[1]} />
                  <Pip src={AVATARS[2]} />
                </div>
                <span className="font-dm-mono text-[8px] text-warning">
                  not for us
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Votes Pending */}
      <div className="flex flex-col gap-1.5">
        <span className="font-dm-mono text-[8px] tracking-[0.12em] uppercase text-ink-500 text-center">
          Votes Pending
        </span>
        <div className="card rounded-[14px] overflow-hidden shadow-md">
          <div className="px-3 py-2 border-b border-ink-700 text-[11px] font-medium text-ink-100">
            Arashiyama
          </div>
          <div className="p-2.5">
            <div className="flex gap-[3px]">
              <span className="flex items-center gap-0.5 px-[5px] py-[2px] rounded-full font-dm-mono text-[7px] bg-success-bg text-success">
                <span className="w-2.5 h-2.5 rounded-full overflow-hidden">
                  <img src={AVATARS[1]} alt="" className="w-full h-full object-cover block" />
                </span>
                SL
              </span>
              <span className="flex items-center gap-0.5 px-[5px] py-[2px] rounded-full font-dm-mono text-[7px] bg-raised text-ink-500 border border-dashed border-ink-700">
                <span className="w-2.5 h-2.5 rounded-full overflow-hidden">
                  <img src={AVATARS[0]} alt="" className="w-full h-full object-cover block" />
                </span>
                you
              </span>
              <span className="flex items-center gap-0.5 px-[5px] py-[2px] rounded-full font-dm-mono text-[7px] bg-raised text-ink-500 border border-dashed border-ink-700">
                <span className="w-2.5 h-2.5 rounded-full overflow-hidden">
                  <img src={AVATARS[2]} alt="" className="w-full h-full object-cover block" />
                </span>
                JR
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Mid-Trip Pivot */}
      <div className="flex flex-col gap-1.5">
        <span className="font-dm-mono text-[8px] tracking-[0.12em] uppercase text-ink-500 text-center">
          Mid-Trip Pivot
        </span>
        <div className="card rounded-[14px] overflow-hidden shadow-md border-accent/40">
          <div className="px-3 py-2 border-b border-ink-700 text-[11px] font-medium text-accent">
            Day 3 &middot; Kyoto
          </div>
          <div className="px-2.5 py-[7px] text-[10px] text-ink-400 opacity-50 border-b border-dashed border-ink-700 italic">
            Arashiyama bamboo &middot; outdoor
          </div>
          <div className="px-2.5 py-2 bg-accent-light border-t border-dashed border-accent/30">
            <div className="font-dm-mono text-[7px] tracking-[0.06em] uppercase text-accent-fg mb-[3px]">
              System &middot; Weather
            </div>
            <div className="text-[9px] text-ink-200 font-normal mb-[5px] leading-[1.4]">
              Rain at 14:00 &middot; swapping outdoor slot
            </div>
            <div className="flex gap-1">
              <span className="font-dm-mono text-[7px] tracking-[0.04em] uppercase rounded-full px-2 py-[3px] bg-accent text-white cursor-pointer">
                Swap It In
              </span>
              <span className="font-dm-mono text-[7px] tracking-[0.04em] uppercase rounded-full px-2 py-[3px] bg-transparent text-ink-400 border border-ink-700 cursor-pointer">
                Keep It
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Dot list helper                                                    */
/* ------------------------------------------------------------------ */

function DotList({ items }: { items: string[] }) {
  return (
    <div className="mt-7 flex flex-col gap-[11px]">
      {items.map((item) => (
        <div key={item} className="flex items-start gap-2.5">
          <div className="w-[5px] h-[5px] rounded-full bg-accent flex-shrink-0 mt-[7px]" />
          <span className="text-[13px] text-ink-400 font-light leading-[1.6]">
            {item}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function LandingPage() {
  return (
    <>
      <LandingNav />

      {/* ==================== HERO ==================== */}
      <section className="relative min-h-[88vh] max-h-[900px] md:min-h-[90vh] md:max-h-[1000px] overflow-hidden max-w-[1600px] mx-auto pt-[62px]">
        {/* Z1: Globe canvas (all breakpoints) */}
        <div className="absolute inset-0 z-[1]">
          <GlobeCanvas />
        </div>

        {/* Z2: Ambient terracotta glow */}
        <div
          className="absolute inset-0 z-[2] pointer-events-none"
          style={{ background: "radial-gradient(ellipse at 72% 52%, rgba(196,105,79,0.06) 0%, transparent 65%)" }}
        />

        {/* Z3: Gradient layers (text protection) */}
        {/* Desktop: left-to-right gradient (text left, globe right) */}
        <div
          className="absolute left-0 inset-y-0 w-[55%] z-[3] pointer-events-none hidden md:block"
          style={{ background: "linear-gradient(to right, var(--bg-base-92) 0%, var(--bg-base-92) 30%, var(--bg-base-60) 50%, transparent 100%)" }}
        />
        {/* Mobile: top-to-bottom gradient (text top, globe bottom) */}
        <div
          className="absolute inset-x-0 top-0 h-[65%] z-[3] pointer-events-none md:hidden"
          style={{ background: "linear-gradient(to bottom, var(--bg-base-92) 0%, var(--bg-base-92) 40%, var(--bg-base-60) 60%, transparent 100%)" }}
        />
        <div
          className="absolute bottom-0 inset-x-0 h-[280px] z-[3] pointer-events-none"
          style={{ background: "linear-gradient(to top, var(--bg-base) 0%, var(--bg-base) 20%, var(--bg-base-92) 50%, transparent 100%)" }}
        />
        <div
          className="absolute top-0 inset-x-0 h-[80px] z-[3] pointer-events-none"
          style={{ background: "linear-gradient(to bottom, var(--bg-base-92) 0%, transparent 100%)" }}
        />
        <div
          className="absolute right-0 inset-y-0 w-[80px] z-[3] pointer-events-none hidden md:block"
          style={{ background: "linear-gradient(to left, var(--bg-base-50) 0%, transparent 100%)" }}
        />

        {/* Z10: Text content */}
        <div className="relative z-[10] flex flex-col justify-center min-h-[inherit] px-6 py-[60px] md:px-14 lg:pl-20 lg:pr-12 max-w-[600px]">
          {/* Eyebrow */}
          <div className="section-eyebrow mb-[22px] animate-[fadeUp_0.7s_ease_both_0.08s]">
            Travel Intelligence
          </div>

          {/* Headline */}
          <h1 className="font-lora text-[clamp(46px,5vw,78px)] font-medium leading-[1.05] tracking-[-0.02em] text-ink-100 mb-6 animate-[fadeUp_0.7s_ease_both_0.16s]">
            The trip that
            <br />
            knows you&apos;re
            <br />
            <em className="italic text-gold">already here.</em>
          </h1>

          {/* Sub */}
          <p className="text-[16px] text-ink-400 font-light leading-[1.74] max-w-[440px] mb-[42px] animate-[fadeUp_0.7s_ease_both_0.24s]">
            Overplanned builds your itinerary from how you actually travel,
            not your demographics. Plans your next trip. Remembers every one
            you&apos;ve taken. Local sources, real-time adaptation, and a plan
            that changes when you do.
          </p>

          {/* Actions */}
          <div className="flex items-center gap-3.5 mb-10 animate-[fadeUp_0.7s_ease_both_0.32s]">
            <a
              href="#waitlist"
              className="btn-primary gap-2 px-[30px] py-3.5 text-[14px] shadow-[0_4px_16px_rgba(196,105,79,0.25)] no-underline"
            >
              <ArrowRightIcon />
              Join the Waitlist
            </a>
            <a
              href="#output"
              className="btn-ghost inline-flex items-center gap-1.5 no-underline"
            >
              See It In Action
              <ArrowRightIcon className="transition-transform group-hover:translate-x-[3px]" />
            </a>
          </div>

          {/* City pills */}
          <div className="flex items-center gap-2.5 flex-wrap animate-[fadeUp_0.7s_ease_both_0.40s]">
            <span className="font-dm-mono text-[9px] tracking-[0.14em] uppercase text-ink-600">
              Featured cities
            </span>
            {["Bend", "Austin", "Nashville", "Asheville"].map((city) => (
              <span
                key={city}
                className="font-dm-mono text-[9px] tracking-[0.06em] text-ink-400 bg-raised border border-ink-700 rounded-full px-2.5 py-[3px]"
              >
                {city}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ==================== THE OUTPUT ==================== */}
      <section
        id="output"
        className="py-[72px] px-6 lg:py-[100px] lg:px-20 bg-base border-t border-ink-700"
      >
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.15fr] gap-16 items-center max-w-[1200px] mx-auto">
          <RevealOnScroll>
            <div className="section-eyebrow mb-3.5">The Output</div>
            <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4">
              A day written
              <br />
              <em className="italic text-gold">for you.</em>
            </h2>
            <p className="text-[15px] text-ink-400 font-light leading-[1.75] max-w-[480px]">
              Not a highlights reel. Slots chosen from behavioral signals, sourced
              from locals, with honest booking states and a suggestion line
              that actually means something.
            </p>
            <DotList
              items={[
                "Source attribution on every slot",
                "Booking states that reflect reality: \"call ahead\" when that's the truth",
                "Busy window signals so you know when to actually arrive",
              ]}
            />
          </RevealOnScroll>
          <RevealOnScroll delay={200}>
            <ItineraryCard />
          </RevealOnScroll>
        </div>
      </section>

      {/* ==================== HOW IT WORKS ==================== */}
      <section
        id="how"
        className="py-[72px] px-6 lg:py-[100px] lg:px-20 bg-warm border-t border-ink-700"
      >
        <RevealOnScroll>
          <div className="text-center max-w-[560px] mx-auto mb-14">
            <div className="section-eyebrow justify-center before:hidden mb-3.5">
              Why It&apos;s Different
            </div>
            <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4 text-center">
              The plan you&apos;d make
              <br />
              <em className="italic text-gold">if you already knew.</em>
            </h2>
            <p className="text-[15px] text-ink-400 font-light leading-[1.75] text-center mx-auto">
              Most travel apps show you the same city. Overplanned shows you yours.
            </p>
          </div>
        </RevealOnScroll>

        <RevealOnScroll delay={100}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-ink-700 border border-ink-700 rounded-[20px] overflow-hidden max-w-[1100px] mx-auto">
            {[
              {
                num: "01",
                title: "Finds the counter seat nobody put on a list",
                body: "The 8-seat ramen spot. The izakaya that only takes walk-ins before 18:00. The coffee bar that opened three months ago. Sources that don't show up on the usual apps.",
                tag: "Local-First",
                tagClass: "bg-success-bg text-success",
              },
              {
                num: "02",
                title: "Builds the plan you'd forget to make",
                body: "Packing lists built from your destination and weather. Budget estimates before you book. Your full itinerary works offline. The stuff that falls through the cracks, handled.",
                tag: "Smart Planning",
                tagClass: "bg-info-bg text-info",
              },
              {
                num: "03",
                title: "Adapts when the trip does",
                body: "Flight delayed. Restaurant closed. Rain all afternoon. The plan reshuffles one slot at a time, not a full rebuild. You approve every change before it happens.",
                tag: "Real-Time",
                tagClass: "bg-accent-light text-accent-fg",
              },
            ].map((cell) => (
              <div
                key={cell.num}
                className="bg-surface hover:bg-warm transition-colors p-[36px_32px]"
              >
                <div className="font-lora text-[36px] md:text-[54px] font-medium italic text-ink-600 leading-none mb-[18px]">
                  {cell.num}
                </div>
                <div className="text-[16px] font-medium text-ink-100 tracking-[-0.01em] mb-2.5 leading-[1.3]">
                  {cell.title}
                </div>
                <div className="text-[13px] text-ink-400 font-light leading-[1.72]">
                  {cell.body}
                </div>
                <span
                  className={`font-dm-mono text-[8px] tracking-[0.1em] uppercase mt-4 inline-block px-[9px] py-[3px] rounded-full ${cell.tagClass}`}
                >
                  {cell.tag}
                </span>
              </div>
            ))}
          </div>
        </RevealOnScroll>
      </section>

      {/* ==================== LOCAL SOURCES ==================== */}
      <section className="py-[72px] px-6 lg:py-[100px] lg:px-20 bg-base border-t border-ink-700">
        <div className="max-w-[1100px] mx-auto">
          <RevealOnScroll>
            <div className="text-center max-w-[560px] mx-auto mb-14">
              <div className="section-eyebrow justify-center before:hidden mb-3.5">
                Local Sources, Not Aggregators
              </div>
              <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4 text-center">
                Intelligence from
                <br />
                <em className="italic text-gold">the ground floor.</em>
              </h2>
              <p className="text-[15px] text-ink-400 font-light leading-[1.75] text-center mx-auto">
                Every recommendation traces back to a real source. We pull from the
                places locals actually use.
              </p>
            </div>
          </RevealOnScroll>

          <RevealOnScroll delay={100}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-[1000px] mx-auto">
              {[
                {
                  icon: (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    </svg>
                  ),
                  title: "Sourced where locals actually look",
                  body: "Regional food blogs. Neighborhood review sites. The kind of places that don't have English translations but have decades of trust. We find them so you don't have to.",
                  tag: "Local-First",
                  tagClass: "bg-success-bg text-success",
                },
                {
                  icon: (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                      <polyline points="23 4 23 10 17 10" />
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                    </svg>
                  ),
                  title: "Always current, never stale",
                  body: "Closures caught before you show up. Hours verified against local sources. Seasonal context baked in.",
                  tag: "Continuous Updates",
                  tagClass: "bg-info-bg text-info",
                },
                {
                  icon: (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    </svg>
                  ),
                  title: "No pay-to-rank. No sponsored slots.",
                  body: "Every recommendation earns its place. No venue pays to appear in your itinerary. No aggregator scores. What you see is what locals actually recommend.",
                  tag: "Zero Sponsored Content",
                  tagClass: "bg-accent-light text-accent-fg",
                },
              ].map((card) => (
                <div
                  key={card.title}
                  className="card rounded-[16px] p-[28px_24px] hover:shadow-md hover:-translate-y-[3px] transition-all duration-300 cursor-default"
                >
                  <div className="w-10 h-10 bg-accent-light rounded-[10px] flex items-center justify-center mb-5 text-accent">
                    {card.icon}
                  </div>
                  <div className="text-[15px] font-medium text-ink-100 tracking-[-0.01em] mb-2.5 leading-[1.3]">
                    {card.title}
                  </div>
                  <div className="text-[13px] text-ink-400 font-light leading-[1.72]">
                    {card.body}
                  </div>
                  <span className={`font-dm-mono text-[8px] tracking-[0.1em] uppercase mt-4 inline-block px-[9px] py-[3px] rounded-full ${card.tagClass}`}>
                    {card.tag}
                  </span>
                </div>
              ))}
            </div>
          </RevealOnScroll>
        </div>
      </section>

      {/* ==================== PERSONA ==================== */}
      <section className="py-[72px] px-6 lg:py-[100px] lg:px-20 bg-base border-t border-ink-700">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center max-w-[1100px] mx-auto">
          <RevealOnScroll delay={200}>
            <PersonaCard />
          </RevealOnScroll>
          <RevealOnScroll>
            <div className="section-eyebrow mb-3.5">Persona System</div>
            <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4">
              Gets sharper
              <br />
              <em className="italic text-gold">every trip.</em>
            </h2>
            <p className="text-[15px] text-ink-400 font-light leading-[1.75] max-w-[480px]">
              No onboarding quiz. No self-reported preferences. Overplanned
              detects travel patterns from what you actually do: what you skip,
              linger on, search after midnight, and book twice.
            </p>
            <DotList
              items={[
                "Compounds across trips, never resets",
                "Updates mid-trip as your energy shifts",
                "Never surfaced as a label. Just better recommendations.",
                "Works offline. Signals sync when you reconnect.",
              ]}
            />
          </RevealOnScroll>
        </div>
      </section>

      {/* ==================== GROUP TRIPS ==================== */}
      <section
        id="group"
        className="py-[72px] px-6 lg:py-[100px] lg:px-20 bg-warm border-t border-ink-700"
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center max-w-[1100px] mx-auto">
          <RevealOnScroll>
            <div className="section-eyebrow mb-3.5">Group Trips</div>
            <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4">
              Four people.
              <br />
              <em className="italic text-gold">One plan.</em>
            </h2>
            <p className="text-[15px] text-ink-400 font-light leading-[1.75] max-w-[480px]">
              Async voting before you leave. Shared packing lists so nobody
              brings three umbrellas. A budget that splits itself. And when the
              trip changes, everyone stays in sync.
            </p>
            <DotList
              items={[
                "Shared packing list. See who's bringing what, skip the duplicates.",
                "Split budget tracker that settles up at the end",
                "Split days: half-day solo, then regroup",
                "Group chat built into the trip, not a separate thread",
              ]}
            />
          </RevealOnScroll>
          <RevealOnScroll delay={200}>
            <GroupPhones />
          </RevealOnScroll>
        </div>
      </section>

      {/* ==================== MAP / TRIP SUMMARY ==================== */}
      <section className="bg-base border-t border-ink-700 overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] max-w-full items-stretch">
          <div className="px-6 py-[72px] lg:px-16 lg:py-20 flex flex-col justify-center">
            <RevealOnScroll>
              <div className="section-eyebrow mb-3.5">Trip Summary</div>
              <h2 className="font-lora text-[clamp(30px,3.5vw,50px)] font-medium tracking-[-0.02em] leading-[1.1] text-ink-100 mb-4">
                Every trip
                <br />
                leaves <em className="italic text-gold">a trace.</em>
              </h2>
              <p className="text-[15px] text-ink-400 font-light leading-[1.75] max-w-[360px]">
                After each trip, Overplanned renders the route you took. Every
                slot, every transit, in the order it happened. Not navigation. Just
                a satisfying artifact of where you actually went, and the data that
                makes your next trip better.
              </p>
              <DotList
                items={[
                  "Compounds into your behavioral profile for next time",
                  "Shareable as an image, or keep it private",
                ]}
              />
            </RevealOnScroll>
          </div>
          <RevealOnScroll delay={200} className="h-full">
            <div className="relative bg-stone border-t lg:border-t-0 lg:border-l border-ink-700 min-h-[420px] h-full">
              <TripMapCanvas />
            </div>
          </RevealOnScroll>
        </div>
      </section>

      {/* ==================== WAITLIST ==================== */}
      <section
        id="waitlist"
        className="py-20 px-6 lg:py-[120px] lg:px-20 bg-warm border-t border-ink-700 text-center relative overflow-hidden"
      >
        {/* Radial glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at 50% 100%, rgba(196,105,79,0.08) 0%, transparent 65%)",
          }}
        />
        <RevealOnScroll className="relative z-[1]">
          <div className="section-eyebrow justify-center before:hidden mb-[18px]">
            Join Overplanned
          </div>
          <h2 className="font-lora text-[clamp(36px,4.5vw,60px)] font-medium tracking-[-0.02em] leading-[1.05] text-ink-100 mb-3.5">
            Travel smarter
            <br />
            from <em className="italic text-gold">day one.</em>
          </h2>
          <p className="text-[15px] text-ink-400 font-light max-w-[400px] mx-auto mb-11 leading-[1.74]">
            First cities at launch: Bend, Austin, Seattle, Nashville, Asheville. iOS
            and Android.
          </p>
          <WaitlistForm />
        </RevealOnScroll>
      </section>

      {/* ==================== FOOTER ==================== */}
      <footer className="border-t border-ink-700 px-6 py-7 lg:px-20 flex items-center justify-between bg-base flex-col gap-2.5 sm:flex-row sm:gap-0">
        <span className="font-sora text-[15px] font-bold tracking-[-0.04em] text-ink-500">
          overplanned<span className="text-accent">.</span>
        </span>
        <span className="font-dm-mono text-[9px] tracking-[0.08em] uppercase text-ink-600">
          We&apos;re type A for people who are type B
        </span>
      </footer>
    </>
  );
}
