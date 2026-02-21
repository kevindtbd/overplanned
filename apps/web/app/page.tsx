import type { Metadata } from "next";
import LandingNav from "@/components/landing/LandingNav";
import RevealOnScroll from "@/components/landing/RevealOnScroll";
import WaitlistForm from "@/components/landing/WaitlistForm";
import GlobeCanvas from "@/components/landing/GlobeCanvas";

export const metadata: Metadata = {
  title: "overplanned. -- Travel that knows you",
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
/*  Itinerary card (static mockup for "The Output" section)           */
/* ------------------------------------------------------------------ */

function ItineraryCard() {
  return (
    <div className="card overflow-hidden shadow-xl rounded-[20px]">
      {/* Header */}
      <div className="flex items-center justify-between px-[18px] py-[14px] border-b border-ink-700">
        <span className="font-sora text-[15px] font-semibold tracking-[-0.02em] text-ink-100">
          Kyoto &middot; Day 3
        </span>
        <span className="font-dm-mono text-[8px] text-ink-500 tracking-[0.08em] uppercase">
          Friday &middot; 4 Slots
        </span>
      </div>
      {/* Day tabs */}
      <div className="flex px-[18px] border-b border-ink-700 overflow-hidden">
        {["Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <span
            key={d}
            className={`py-2 px-2.5 font-dm-mono text-[8px] tracking-[0.08em] uppercase cursor-pointer whitespace-nowrap border-b-2 ${
              d === "Fri"
                ? "text-ink-100 border-accent"
                : "text-ink-500 border-transparent"
            }`}
          >
            {d}
          </span>
        ))}
      </div>
      {/* Slot 1: Fushimi Inari */}
      <div className="flex items-stretch border-b border-ink-700 hover:bg-warm transition-colors cursor-pointer">
        <div className="w-[72px] h-[72px] flex-shrink-0 overflow-hidden relative">
          <img
            src="https://images.unsplash.com/photo-1478436127897-769e1b3f0f36?w=300&q=70&auto=format&fit=crop"
            alt="Fushimi Inari"
            className="w-full h-full object-cover block hover:scale-[1.06] transition-transform duration-400"
          />
          <span className="absolute bottom-1 left-1 font-dm-mono text-[7px] tracking-[0.04em] uppercase px-[5px] py-[1px] rounded-full bg-[rgba(61,122,82,0.88)] text-white">
            Visited
          </span>
        </div>
        <div className="flex-1 px-3.5 py-2.5 flex flex-col justify-center">
          <span className="text-[13px] font-medium text-ink-100 mb-0.5">
            Fushimi Inari
          </span>
          <span className="text-[11px] text-ink-400 font-light italic mb-1">
            left before the crowds hit
          </span>
          <div className="flex gap-1 flex-wrap">
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-success-bg text-success">
              Local
            </span>
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-info-bg text-info">
              Tabelog &middot; 2.1k
            </span>
          </div>
        </div>
      </div>
      {/* Transit */}
      <div className="flex items-center gap-1.5 px-3.5 py-1.5 bg-raised border-b border-ink-700">
        <TruckIcon />
        <span className="font-dm-mono text-[9px] text-ink-500">
          18 min taxi &middot; &yen;1,200
        </span>
      </div>
      {/* Slot 2: Kinkaku-ji (active) */}
      <div className="flex items-stretch border-b border-ink-700 bg-accent-light border-l-[3px] border-l-accent cursor-pointer">
        <div className="w-[72px] h-[72px] flex-shrink-0 overflow-hidden relative">
          <img
            src="https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=300&q=70&auto=format&fit=crop"
            alt="Kinkaku-ji"
            className="w-full h-full object-cover block"
          />
          <span className="absolute bottom-1 left-1 font-dm-mono text-[7px] tracking-[0.04em] uppercase px-[5px] py-[1px] rounded-full bg-[rgba(61,122,82,0.88)] text-white">
            Booked
          </span>
        </div>
        <div className="flex-1 px-3.5 py-2.5 flex flex-col justify-center">
          <span className="text-[13px] font-medium text-ink-100 mb-0.5">
            Kinkaku-ji
          </span>
          <span className="text-[11px] text-ink-400 font-light italic mb-1">
            weekday afternoon &middot; thins out by 15:00
          </span>
          <div className="flex gap-1 flex-wrap">
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-success-bg text-success">
              Local
            </span>
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-info-bg text-info">
              Tabelog &middot; 4.2k
            </span>
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-warning-bg text-warning">
              Busy 10-14
            </span>
          </div>
        </div>
      </div>
      {/* Slot 3: Pontocho izakaya */}
      <div className="flex items-stretch hover:bg-warm transition-colors cursor-pointer">
        <div className="w-[72px] h-[72px] flex-shrink-0 overflow-hidden relative">
          <img
            src="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=300&q=70&auto=format&fit=crop"
            alt="Pontocho izakaya"
            className="w-full h-full object-cover block hover:scale-[1.06] transition-transform duration-400"
          />
          <span className="absolute bottom-1 left-1 font-dm-mono text-[7px] tracking-[0.04em] uppercase px-[5px] py-[1px] rounded-full bg-[rgba(26,22,18,0.6)] text-white/[0.92]">
            Book Now
          </span>
        </div>
        <div className="flex-1 px-3.5 py-2.5 flex flex-col justify-center">
          <span className="text-[13px] font-medium text-ink-100 mb-0.5">
            Pontocho izakaya
          </span>
          <span className="text-[11px] text-ink-400 font-light italic mb-1">
            locals-only counter &middot; full by 20:00
          </span>
          <div className="flex gap-1 flex-wrap">
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-success-bg text-success">
              Local
            </span>
            <span className="font-dm-mono text-[8px] px-1.5 py-0.5 rounded-full bg-info-bg text-info">
              Tabelog &middot; 3.8k
            </span>
          </div>
        </div>
      </div>
    </div>
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
            Arashiyama bamboo -- outdoor
          </div>
          <div className="px-2.5 py-2 bg-accent-light border-t border-dashed border-accent/30">
            <div className="font-dm-mono text-[7px] tracking-[0.06em] uppercase text-accent-fg mb-[3px]">
              System &middot; Weather
            </div>
            <div className="text-[9px] text-ink-200 font-normal mb-[5px] leading-[1.4]">
              Rain at 14:00 -- swapping outdoor slot
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
      <section className="min-h-screen grid grid-cols-1 lg:grid-cols-2 pt-[62px] overflow-hidden">
        {/* Left */}
        <div className="flex flex-col justify-center px-6 py-[60px] md:px-14 lg:pl-20 lg:pr-12">
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
            Overplanned builds your itinerary from how you actually travel -- not
            your demographics. Local sources. Real-time adaptation. A plan that
            changes when you do.
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
              First cities
            </span>
            {["Tokyo", "Kyoto", "Seoul", "Barcelona"].map((city) => (
              <span
                key={city}
                className="font-dm-mono text-[9px] tracking-[0.06em] text-ink-400 bg-raised border border-ink-700 rounded-full px-2.5 py-[3px]"
              >
                {city}
              </span>
            ))}
          </div>
        </div>

        {/* Right: Globe placeholder (desktop only) */}
        <div className="hidden lg:flex relative bg-warm items-center justify-center overflow-hidden">
          {/* Left-edge gradient fade */}
          <div className="absolute left-0 top-0 w-20 h-full bg-gradient-to-r from-base to-transparent z-[2] pointer-events-none" />
          {/* Bottom gradient fade */}
          <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-base to-transparent z-[2] pointer-events-none" />
          <GlobeCanvas />

          {/* Floating cards */}
          <div className="absolute z-[3] top-[20%] left-[7%] card rounded-[14px] shadow-lg p-[10px_14px] animate-[floatCard_7s_ease-in-out_infinite]">
            <div className="font-dm-mono text-[8px] tracking-[0.1em] uppercase text-accent-fg mb-[3px]">
              Kyoto &middot; Day 3
            </div>
            <div className="text-[12px] font-medium text-ink-100 mb-[2px]">
              Kinkaku-ji
            </div>
            <div className="text-[10px] text-ink-400 font-light italic">
              weekday &middot; thins out by 15:00
            </div>
            <span className="font-dm-mono text-[8px] text-info bg-info-bg px-1.5 py-0.5 rounded-full inline-block mt-[5px]">
              Tabelog &middot; 4.2k
            </span>
          </div>

          <div className="absolute z-[3] bottom-[26%] right-[7%] card rounded-[14px] shadow-lg p-[10px_14px] animate-[floatCard_7s_ease-in-out_infinite_-2.5s]">
            <div className="font-dm-mono text-[8px] tracking-[0.1em] uppercase text-accent-fg mb-[3px]">
              Tokyo &middot; Day 1
            </div>
            <div className="text-[12px] font-medium text-ink-100 mb-[2px]">
              Tsukiji outer market
            </div>
            <div className="text-[10px] text-ink-400 font-light italic">
              locals-only &middot; 06:00 counter
            </div>
            <span className="font-dm-mono text-[8px] text-info bg-info-bg px-1.5 py-0.5 rounded-full inline-block mt-[5px]">
              Tabelog &middot; 8.1k
            </span>
          </div>

          <div className="absolute z-[3] top-[54%] left-[5%] card rounded-[14px] shadow-lg p-[10px_14px] animate-[floatCard_7s_ease-in-out_infinite_-5s]">
            <div className="font-dm-mono text-[8px] tracking-[0.1em] uppercase text-accent-fg mb-[3px]">
              Seoul &middot; Pivot
            </div>
            <div className="text-[12px] font-medium text-ink-100 mb-[2px]">
              Rain at 14:00 &rarr;
            </div>
            <div className="text-[10px] text-ink-400 font-light italic">
              swapping to indoor alternative
            </div>
          </div>
        </div>
      </section>

      {/* Globe banner -- mobile only */}
      <div className="lg:hidden relative h-[280px] bg-warm border-b border-ink-700 overflow-hidden">
        <div className="absolute bottom-0 left-0 right-0 h-[60px] bg-gradient-to-t from-base to-transparent pointer-events-none z-[2]" />
        <GlobeCanvas />
      </div>

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
              that&apos;s specific -- not &ldquo;great for foodies.&rdquo;
            </p>
            <DotList
              items={[
                "Source attribution on every slot -- not a black box",
                "Booking states that reflect reality -- \"call ahead\" when that's the truth",
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
              Most travel apps show you the same city. Overplanned shows you your
              city -- the one that fits how you actually move through the world.
            </p>
          </div>
        </RevealOnScroll>

        <RevealOnScroll delay={100}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-ink-700 border border-ink-700 rounded-[20px] overflow-hidden max-w-[1100px] mx-auto">
            {[
              {
                num: "01",
                title: "Finds the counter seat nobody put on a list",
                body: "The 8-seat ramen spot. The izakaya that only takes walk-ins before 18:00. The coffee bar that opened three months ago. Sources that don't translate, aggregated so you don't have to.",
                tag: "Local-First",
                tagClass: "bg-success-bg text-success",
              },
              {
                num: "02",
                title: "Knows what kind of tired you are",
                body: 'Day four tired is different from day one tired. A quick coffee break tired is different from "cancel the afternoon" tired. The plan adjusts -- one slot, not a rebuild -- without you having to explain yourself.',
                tag: "Reads the Room",
                tagClass: "bg-info-bg text-info",
              },
              {
                num: "03",
                title: "Gets better every time you use it",
                body: "Every trip compounds. The more you travel, the sharper your recommendations get -- not because you filled out a profile, but because the system watched what you actually chose, skipped, and lingered on.",
                tag: "Compounds Over Time",
                tagClass: "bg-accent-light text-accent-fg",
              },
            ].map((cell) => (
              <div
                key={cell.num}
                className="bg-surface hover:bg-warm transition-colors p-[36px_32px]"
              >
                <div className="font-lora text-[54px] font-medium italic text-ink-700 leading-none mb-[18px]">
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
              detects travel patterns from what you actually do -- what you skip,
              linger on, search after midnight, and book twice.
            </p>
            <DotList
              items={[
                "Compounds across trips -- not reset each time",
                "Updates mid-trip -- tired on day four reads differently than tired on day one",
                "Never surfaced as a label -- translated directly into what you see",
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
              Async voting before you leave. The system tracks who keeps
              compromising -- not just who wins the vote -- and rebalances across
              the trip. Conflicts surface as two camps, not a debate thread nobody
              reads.
            </p>
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
                After each trip, Overplanned renders the route you took -- every
                slot, every transit, in the order it happened. Not navigation. Just
                a satisfying artifact of where you actually went, and the data that
                makes your next trip better.
              </p>
              <DotList
                items={[
                  "Compounds into your behavioral profile for next time",
                  "Shareable -- export as an image or keep it private",
                ]}
              />
            </RevealOnScroll>
          </div>
          <RevealOnScroll delay={200}>
            <div className="relative bg-stone border-t lg:border-t-0 lg:border-l border-ink-700 min-h-[360px] flex items-center justify-center">
              {/* Placeholder for the trip map canvas -- static representation */}
              <div className="w-full h-full min-h-[360px] p-8 flex items-center justify-center">
                <div className="text-ink-500 font-dm-mono text-[10px] tracking-[0.08em] uppercase">
                  Trip route visualization
                </div>
              </div>
              {/* Map legend */}
              <div className="absolute bottom-[18px] right-[18px] card rounded-[10px] p-[10px_14px] flex flex-col gap-[5px]">
                {[
                  { color: "bg-success", label: "Start" },
                  { color: "bg-ink-500", label: "Visited" },
                  { color: "bg-accent", label: "End" },
                ].map((item) => (
                  <div key={item.label} className="flex items-center gap-[7px]">
                    <div
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${item.color}`}
                    />
                    <span className="font-dm-mono text-[8px] tracking-[0.06em] uppercase text-ink-400">
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
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
            First cities at launch: Tokyo, Kyoto, Osaka, Seoul, Barcelona. iOS
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
          Built on behavioral signals, not demographics
        </span>
      </footer>
    </>
  );
}
