**WAYMARK**

**Deep Dive Agenda**

Six unresolved areas · Key questions per topic · Decision dependencies

Each section captures the current thinking, the open questions that
require a decision before building, and why it matters to get it right.
These are not technical specs --- they\'re the product and architecture
decisions that Claude Code cannot make on its own.

  -------------------------------------------------------------------------
  **Topic**               **Status**       **Blocks**
  ----------------------- ---------------- --------------------------------
  **Monetization**        **UNRESOLVED**   Onboarding design, feature
                                           gating, group architecture,
                                           pricing tier

  **Real-Time             **AWAITING DEEP  Mid-trip UX, cascade logic,
  Reactivity**            DIVE**           event architecture

  **Onboarding Flow**     **FRAMES ONLY**  Cold start quality, persona
                                           seed, first-impression retention

  **Post-Trip             **STUB ONLY**    Retention loop, behavioral
  Experience**                             signal quality, memory layer

  **Search & Discovery**  **NOT STARTED**  Navigation architecture,
                                           inspiration mode, contextual
                                           search

  **Safety, Trust & Data  **NOT STARTED**  Legal exposure, data freshness,
  Quality**                                abuse vectors
  -------------------------------------------------------------------------

**1. Monetization**

  ---------------- --------------------------------------------------------------
  **UNRESOLVED**   Must be decided before onboarding design, feature gating, or
                   group architecture is finalized.

  ---------------- --------------------------------------------------------------

The paywall position determines almost everything downstream. It affects
what gets built first, how onboarding is sequenced, what the group
architecture looks like, and what the data model tracks. This cannot be
designed after the fact.

**Current State**

The philosophy doc flags it as an open design question. The notification
doc references a post-trip email. Nothing else. No pricing model, no
tier definition, no paywall position, no group billing model. Completely
undesigned.

**Core Tension**

Overplanned\'s value --- local intelligence, personalization --- compounds
over time. A paywall too early kills the data flywheel before it starts.
Too late and there\'s no revenue. The free tier has to be genuinely good
enough to collect behavioral data, but paid has to be clearly better.

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **What is the monetization model?**                              |
| Q1 |                                                                  |
| ** | Subscription vs. per-trip vs. freemium vs. B2B vs. hybrid. Each  |
|    | has different implications for architecture and user psychology. |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What does free actually give you?**                            |
| Q2 |                                                                  |
| ** | Tease-and-lock kills data collection. The free tier needs to     |
|    | deliver real value AND create a clear ceiling. What\'s the       |
|    | ceiling?                                                         |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **Is the group trip the natural monetization wedge?**            |
| Q3 |                                                                  |
| ** | Solo trip free, group trip paid (trip creator pays). Natural     |
|    | because the coordination value is obvious and the social dynamic |
|    | makes payment feel like hosting, not a paywall.                  |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What is the paywall moment?**                                  |
| Q4 |                                                                  |
| ** | Mid-planning friction is the worst possible place. Best: a       |
|    | natural level-up moment --- adding a second group member,        |
|    | requesting a re-plan mid-trip, activating a second concurrent    |
|    | trip.                                                            |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **Is there a B2B angle?**                                        |
| Q5 |                                                                  |
| ** | Pipeline C\'s local intelligence layer is valuable to travel     |
|    | agencies, hotel concierges, corporate travel desks. Different    |
|    | revenue model, different build priority. Worth deciding early if |
|    | yes.                                                             |
+----+------------------------------------------------------------------+

**Thought Starters**

-   Group trip as the wedge: solo free forever, group trip creator pays
    \~\$12--15 per trip or \~\$8/month subscription. Group members never
    pay.

-   Per-trip pricing: pay once per destination (\~\$4--6), own that
    destination\'s recommendations indefinitely. No subscription
    fatigue.

-   Annual subscription (\$40--60/year) with free tier limited to 1
    active trip at a time, basic persona only, no group features.

-   B2B: license the ActivityNode + Pipeline C data to travel businesses
    at \$X/month API access. Consumer app stays free as a marketing
    channel.

-   The Duolingo model: free but the premium features are clearly
    better, not locked arbitrarily. Streaks, advanced persona, trip
    history analysis = premium.

**What Getting This Wrong Looks Like**

-   Paywall at trip generation → user never sees the product\'s value,
    churns before forming a habit

-   No free tier ceiling → impossible to convert, no revenue,
    unsustainable

-   Per-person group billing → feels punitive, kills group adoption, one
    person always left paying for others

-   B2B without deciding it early → consumer features built in ways that
    make the API hard to expose later

**2. Real-Time Reactivity Layer**

  ------------ --------------------------------------------------------------
  **AWAITING   Explicitly deferred in architecture doc. The feature that
  DEEP DIVE**  makes Overplanned feel alive mid-trip vs. a static PDF.

  ------------ --------------------------------------------------------------

The architecture doc calls this one of the most important unsolved
problems and immediately defers it. Re-vectoring speed, cascade effects,
mood signals, adjacent/polar opposite swaps. Without this, Overplanned is a
better itinerary generator, not a better travel companion.

**Current State**

Architecture doc Section 8 identifies the problem space --- mood shifts,
cancellations, delays, chain effects --- and sets a latency target (\<2s
single-slot swap, \<5s full day re-solve). It mentions pre-computed
fallback graphs and event-driven cascade evaluation. No implementation,
no data model, no UX design for the \'your plan changed\' moment.

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **Pre-computed fallback graphs vs. on-the-fly recomputation?**   |
| Q1 |                                                                  |
| ** | Pre-computing adjacent + polar-opposite alternatives per slot is |
|    | cheaper at serving time but requires storage and nightly         |
|    | refresh. On-the-fly is flexible but has latency risk. Probably:  |
|    | pre-compute for known slots, on-the-fly for novel pivots.        |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How do we capture mood without being annoying?**               |
| Q2 |                                                                  |
| ** | Passive signals (pace of completion, skip patterns,              |
|    | time-between-interactions) vs. active prompts (emoji check-in,   |
|    | quick question). The active route has to be earned --- you       |
|    | can\'t ask after every slot.                                     |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What\'s the cascade model?**                                   |
| Q3 |                                                                  |
| ** | When slot 2 of 6 shifts, which downstream slots are affected and |
|    | in what order? Naive: recompute all. Smart: dependency graph     |
|    | where only transitively affected slots are re-evaluated. Need a  |
|    | formal model.                                                    |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **Push notification vs. in-app surface for \'your plan           |
| Q4 | changed\'?**                                                     |
| ** |                                                                  |
|    | Push if user is not in app (restaurant closed, transit delayed). |
|    | In-app drawer if they\'re active. The message tone matters ---   |
|    | alarming vs. calm reassurance that the system handled it.        |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How does group state complicate real-time reactivity?**        |
| Q5 |                                                                  |
| ** | One member\'s mood shift in a group of 4 shouldn\'t replan the   |
|    | whole day. Threshold model: does the majority feel the same? Do  |
|    | we poll first? Who has override authority?                       |
+----+------------------------------------------------------------------+

**What Needs to Be Designed**

-   The fallback graph data structure --- what gets pre-computed per
    slot, how stale does it go, when does it get refreshed

-   The cascade dependency model --- which slots are \'downstream\' of a
    given change, formal rules

-   Mood signal taxonomy --- what passive signals map to what mood
    states, what active prompts exist and when they fire

-   The \'plan changed\' UX --- what the user sees, what they can do,
    how intrusive it is

-   Group reactivity rules --- threshold for replanning, poll-first vs.
    act-first, override model

**Why It Matters**

This is the feature that separates a planning app from a travel
companion. Every competitor gives you a static itinerary. The moment
someone\'s day changes --- restaurant closed, it\'s raining, you\'re
more tired than expected --- that\'s when Overplanned either earns trust or
breaks it. The architecture has to be designed before implementation,
not discovered during it.

**3. Onboarding Flow**

  ---------- --------------------------------------------------------------
  **FRAMES   Cold start architecture exists. Actual screen design, question
  ONLY**     sequence, and persona seed logic are undesigned.

  ---------- --------------------------------------------------------------

Every user hits onboarding. The quality of the persona seed it produces
determines recommendation quality on the first trip --- which determines
whether the user comes back for a second. The architecture doc has the
data model. The UX flow is a blank slate.

**Current State**

The addendum has preset templates (couples_slow, group_packed, etc.)
with persona dimension seeds. The open questions doc notes scenario
cards as a design idea, immediately deferred. The cold start ML section
established that 6--8 persona dimensions before trip one is a structural
advantage. None of this is a screen design or a user flow.

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **What\'s the first question?**                                  |
| Q1 |                                                                  |
| ** | \'Who\'s going?\' is the most natural entry point --- sets       |
|    | solo/group mode immediately, which branches the entire           |
|    | experience. Or does destination come first? Order matters        |
|    | because it frames intent.                                        |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How do we collect persona without it feeling like a form?**    |
| Q2 |                                                                  |
| ** | The tag selection UX, preset cards, scenario-based questions --- |
|    | all ideas, none designed. The experience has to feel like        |
|    | planning, not profiling. The distinction is emotional: am I      |
|    | choosing who I am, or am I getting to know a place?              |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How many questions is too many?**                              |
| Q3 |                                                                  |
| ** | Each question is a persona signal. But every additional question |
|    | is friction before the user sees value. The Spotify \'pick 3     |
|    | artists\' model: 3 choices, immediate payoff. What\'s the travel |
|    | equivalent minimum viable persona?                               |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What does the user see immediately after?**                    |
| Q4 |                                                                  |
| ** | The first generated itinerary IS the product\'s pitch. If it\'s  |
|    | generic, the user bounces. If it\'s startlingly good, they\'re   |
|    | hooked. The gap between onboarding quality and first output is   |
|    | the product\'s hardest design challenge.                         |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How does group onboarding work?**                              |
| Q5 |                                                                  |
| ** | Solo onboarding is one person answering. Group onboarding is     |
|    | async --- the trip creator goes first, then other members join   |
|    | and answer separately. The system can\'t generate until it has   |
|    | enough members\' persona seeds. How long does it wait? What does |
|    | the \'waiting for others\' state look like?                      |
+----+------------------------------------------------------------------+

**What Needs to Be Designed**

-   Question sequence and branching logic --- what gets asked in what
    order, where it branches based on answers

-   The tag/card selection UX --- how persona tags are presented,
    selected, what selecting feels like

-   Preset template presentation --- do presets come before or after
    individual questions?

-   First itinerary generation moment --- the reveal, how long it takes,
    what the loading state communicates

-   Group async onboarding --- invite flow, waiting state, partial
    persona generation

-   Skip / \'figure it out as we go\' path --- what happens if someone
    refuses to answer? Do we let them?

**Design Principle to Lock In**

  --------------- --------------------------------------------------------------
  **PRINCIPLE**   Onboarding should feel like anticipation, not intake. The user
                  should end it more excited about their trip than when they
                  started --- not relieved it\'s over.

  --------------- --------------------------------------------------------------

**4. Post-Trip Experience & Retention Loop**

  -------- --------------------------------------------------------------
  **STUB   24hr push prompt and 7-day email exist in notification doc. No
  ONLY**   product design beyond that.

  -------- --------------------------------------------------------------

The post-trip experience is the retention mechanism and the behavioral
signal quality amplifier. Every completed trip should make the next one
meaningfully better --- and the user should feel that. Currently
there\'s a prompt and an email. That\'s a trigger, not a product.

**Current State**

Notification doc: 24hr post-trip push (\'How was it? Tell us the one
thing that surprised you\'), 7-day email (\'Your Kyoto trip, saved\').
No screen design, no memory layer, no feedback loop architecture, no
connection between post-trip signal and next-trip quality.

**Three Things the Post-Trip Product Could Be**

**A. The Memory Layer**

Your trips, saved --- not as an itinerary printout but as a living
record. What you planned vs. what you did. Notes you made. Photos linked
by location. Moments you highlighted. This is also a retention
mechanism: every completed trip makes Overplanned more yours. The more trips
in your history, the harder it is to leave.

**B. The Feedback Loop**

Higher-quality behavioral signal than anything captured mid-trip.
Post-trip, the user can reflect --- this was the highlight, we skipped
this and don\'t regret it, the restaurant was worse than rated. The UX
has to earn this feedback: no star ratings, no forms. Something more
like a highlight reel you curate, or a single open-ended question that
reveals something.

**C. The Re-Planning Seed**

The post-trip experience should make the next trip\'s recommendations
visibly better. That connection needs to be explicit --- the user should
feel the system getting smarter. \'Because you loved the standing bars
in Osaka, here\'s what we\'re thinking for Tokyo.\' That sentence is the
product\'s long-term value proposition.

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **What form does post-trip reflection take?**                    |
| Q1 |                                                                  |
| ** | Highlight reel? Single open-ended question? Curated \'moments\'  |
|    | feed? Something photo-based? The format determines the signal    |
|    | quality and the retention value.                                 |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How do we distinguish \'planned but skipped\' from \'planned,  |
| Q2 | went, disliked\'?**                                              |
| ** |                                                                  |
|    | These are completely different signals. Currently the system     |
|    | might interpret a skipped slot as rejection when it was just a   |
|    | time constraint. Post-trip is the chance to disambiguate --- but |
|    | only if the UX asks the right question.                          |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How explicit should the \'system got smarter\' communication   |
| Q3 | be?**                                                            |
| ** |                                                                  |
|    | Show the user their persona evolution? Tell them what the next   |
|    | recommendation changed because of this trip? Or keep it          |
|    | invisible and just deliver better results? Transparency vs.      |
|    | magic.                                                           |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What\'s the shared trip artifact?**                            |
| Q4 |                                                                  |
| ** | The 7-day email links to a \'shared trip view.\' What is that    |
|    | actually? A public URL? Auto-created? Who can see it? How does   |
|    | it relate to the shared trips architecture already designed?     |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **When does post-trip become pre-trip for the next               |
| Q5 | destination?**                                                   |
| ** |                                                                  |
|    | The transition from reflecting on Kyoto to planning Tokyo is the |
|    | highest-value moment for re-engagement. How does the system      |
|    | recognize and surface that moment?                               |
+----+------------------------------------------------------------------+

**What Needs to Be Designed**

-   The post-trip screen --- what the user sees when they open the app
    the day after returning

-   The reflection UX --- how feedback is collected, what it looks and
    feels like

-   The memory artifact --- how past trips are stored, browsed,
    revisited

-   The \'system got smarter\' signal --- how (or whether) persona
    evolution is communicated

-   The re-engagement hook --- how post-trip naturally transitions to
    next-trip planning

**5. Search & Discovery Surface**

  ----------- --------------------------------------------------------------
  **NOT       On hold pending brand direction. No mental model, no screen
  STARTED**   design, no architecture.

  ----------- --------------------------------------------------------------

Search is a fundamental user need that hasn\'t been modeled at all.
Someone arrives and types \'Tokyo\' --- or they don\'t know where
they\'re going and need to be inspired. Three completely different
modes, each requiring a different surface.

**The Three Search Modes**

**Mode 1 --- \'I Know Where I\'m Going\'**

Destination search. User types Tokyo. The question is what the result
looks like. Generic results list: forgettable. Trip template to
customize: functional. Editorial \'here\'s Overplanned\'s take on Tokyo\':
differentiated. The editorial model aligns with the brand philosophy and
gives the local intelligence a place to live before personalization
kicks in.

**Mode 2 --- \'I Don\'t Know Where I\'m Going\'**

Inspiration mode. Nobody does this well. Spotify for travel: you don\'t
pick a song, you pick a vibe and it finds the destination. \'Slow,
food-heavy, warm weather, not too far from Seattle\' → here are three
cities. This is technically interesting (destination recommendation is a
different model than activity recommendation) and brand-defining. It\'s
also highest build complexity.

**Mode 3 --- \'I\'m Already There\'**

Contextual search. Mid-trip, right now, near me. User has a specific
need --- \'I want coffee that isn\'t Starbucks\' --- and needs a smart
filter, not a ranked list. This is the offline swipe deck but with
intent. Closest to solved since the ActivityNode infrastructure supports
it.

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **Which mode is the primary entry point?**                       |
| Q1 |                                                                  |
| ** | The home screen defaults to one of these. The choice defines the |
|    | product\'s identity. Destination-first = planning tool.          |
|    | Inspiration-first = travel companion. Contextual-first = in-trip |
|    | assistant.                                                       |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What does the destination result look like?**                  |
| Q2 |                                                                  |
| ** | List of activities? An editorial intro? A \'Overplanned\'s take\'    |
|    | card before personalization? The first screen after searching    |
|    | \'Tokyo\' is the product demo --- it has to be spectacular.      |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How does inspiration mode work technically?**                  |
| Q3 |                                                                  |
| ** | Destination recommendation requires a different model than       |
|    | activity recommendation. User vibe → destination mapping isn\'t  |
|    | in the current architecture. Does it exist as a feature at v1 or |
|    | is it a later addition?                                          |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **Is there a browse/editorial surface?**                         |
| Q4 |                                                                  |
| ** | The discovery doc floats an editorial frame --- curated          |
|    | destinations, seasonal picks, \'trending with people like you.\' |
|    | This is a content operation as much as a product feature. Does   |
|    | Overplanned want to be in the editorial business?                    |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How does search relate to onboarding?**                        |
| Q5 |                                                                  |
| ** | If a user searches \'Tokyo\' before completing onboarding, do we |
|    | interrupt with persona setup or let them see a generic result    |
|    | first? The sequence affects conversion and data quality.         |
+----+------------------------------------------------------------------+

**What Needs to Be Designed**

-   Home screen information architecture --- what state does an existing
    user see vs. new user

-   Destination search result --- the screen after typing a city name,
    before personalization

-   Inspiration mode --- does it exist at v1, and if so, what\'s the
    minimum viable version

-   Browse/editorial surface --- yes or no decision, then design if yes

-   Search-before-onboarding flow --- what happens, in what order

**6. Safety, Trust & Data Quality**

  ----------- --------------------------------------------------------------
  **NOT       Three distinct problem categories. Legal exposure, data
  STARTED**   staleness, and abuse vectors --- each needs separate thinking.

  ----------- --------------------------------------------------------------

Three distinct safety problems masquerading as one. Data quality is an
ML problem. Identity-specific safety is a product and ethics problem.
Abuse vectors are a security problem. They need separate thinking, but
they\'re all missing.

**Problem A --- Data Freshness & Staleness**

ActivityNodes go stale. A Tabelog review from 2019 for a restaurant that
changed chefs in 2022 is actively misleading. The scraping cadence
handles currency at the source level, but there\'s no model for
confidence decay on stored ActivityNode signals over time --- analogous
to persona dimension decay but applied to venues.

-   What\'s the half-life of a quality_signal by source type? (Tabelog
    review vs. Reddit thread vs. blog post)

-   How does a venue closure get detected and propagated? Google Places
    API provides some of this --- but what\'s the fallback?

-   What happens when Pipeline C\'s data contradicts itself across
    sources? (High Tabelog score, recent Reddit thread saying it\'s
    declined)

-   What does the user see when an ActivityNode\'s confidence score is
    low? Do we show it at all?

**Problem B --- Identity-Specific Safety**

The current architecture has tourist_score, crowd_model, and some safety
signals. None of it handles identity-specific safety. An LGBTQ+ traveler
in a country where homosexuality is criminalized needs different
recommendations than a straight traveler. A solo woman at night needs
different signals than a group of four. These aren\'t edge cases ---
they\'re significant user populations with real safety stakes.

-   Does Overplanned collect identity information for safety filtering? If
    so, how, when, and how is it stored?

-   If not, how does the system handle safety without knowing who needs
    what?

-   LGBTQ+ safety indexes (Equaldex, ILGA) are already listed in the
    data sources doc --- but they\'re not connected to recommendation
    logic

-   What\'s the legal exposure if Overplanned recommends a venue that turns
    out to be unsafe for a specific user?

-   Does the app have a \'safety mode\' toggle, or is safety filtering
    always-on at the destination level?

**Problem C --- Abuse Vectors**

Three attack surfaces that haven\'t been modeled as security problems:
shared trip links, the group invite flow, and the Pipeline C data
pipeline.

-   Shared trip links: can a malicious link inject bad ActivityNode data
    into a recipient\'s recommendations? What\'s the trust model for
    imported content?

-   Cross-reference confidence gaming: can a coordinated set of fake
    blog posts or Reddit accounts inflate a venue\'s confidence score?
    The authority scoring model is the defense --- but it hasn\'t been
    stress-tested as a security model.

-   Group invite abuse: can someone join a group trip they weren\'t
    intended for? What\'s the invite validation model?

-   LLM extraction poisoning: if a malicious review gets into the
    scraped corpus, can it influence what the LLM extracts as structured
    signals?

**Key Questions to Resolve**

+----+------------------------------------------------------------------+
| ** | **Does Overplanned collect identity info for safety filtering?**     |
| Q1 |                                                                  |
| ** | Binary decision with large downstream implications. Yes: enables |
|    | personalized safety, creates data sensitivity and legal          |
|    | obligations. No: requires a different approach ---               |
|    | destination-level safety signals, opt-in disclosures.            |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What is the freshness model for ActivityNodes?**               |
| Q2 |                                                                  |
| ** | Confidence decay constants by source type, venue closure         |
|    | detection, conflict resolution between sources. Needs a formal   |
|    | model analogous to the persona decay system.                     |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **What\'s the legal posture on recommendations?**                |
| Q3 |                                                                  |
| ** | Is Overplanned a platform (not responsible for venue quality) or a   |
|    | recommendation service (has duty of care)? This is a legal       |
|    | question but it determines product design --- disclaimers,       |
|    | safety warnings, how assertive recommendations can be.           |
+----+------------------------------------------------------------------+

+----+------------------------------------------------------------------+
| ** | **How resilient is the authority scoring model to gaming?**      |
| Q4 |                                                                  |
| ** | The cross-reference confidence scorer was designed for quality   |
|    | signal, not adversarial robustness. Are there rate limits on how |
|    | fast a venue\'s score can increase? Are new sources treated with |
|    | lower initial trust?                                             |
+----+------------------------------------------------------------------+

**Why This Can\'t Wait**

  ---------- --------------------------------------------------------------
  **RISK**   A recommendation that sends someone somewhere unsafe, or stale
             data that sends someone to a closed venue, is a
             trust-destroying event. Safety isn\'t a post-launch polish
             item. It needs to be designed in from the start --- even if
             the implementation is simple at v1.

  ---------- --------------------------------------------------------------

**Decision Dependencies**

Some of these decisions are prerequisites for others. Suggested order
for deep dive sessions:

  ------------------------------------------------------------------------------
  **\#**   **Topic**          **Depends On** **Unblocks**
  -------- ------------------ -------------- -----------------------------------
  1        **Monetization**   Nothing        Onboarding design, feature gating,
                                             group billing, build priority

  2        **Safety & Trust** Nothing        Legal posture, data model for
                                             identity signals, Pipeline C design

  3        **Onboarding       Monetization   First-trip quality, persona seed
           Flow**             (what\'s       design, group async invite flow
                              gated)         

  4        **Search &         Onboarding     Home screen architecture,
           Discovery**        (entry         inspiration mode, editorial
                              sequence)      strategy

  5        **Real-Time        Core           Mid-trip UX, cascade model, group
           Reactivity**       architecture   reactivity rules
                              (done)         

  6        **Post-Trip        Onboarding,    Retention loop, memory layer,
           Experience**       Reactivity     re-engagement hook
  ------------------------------------------------------------------------------

Monetization and Safety can be resolved in parallel --- neither depends
on the other. Everything else flows from Monetization first.
