"use client";

import { useState, type FormEvent } from "react";

export default function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email || !email.includes("@")) {
      setError(true);
      setTimeout(() => setError(false), 1500);
      return;
    }
    setSubmitted(true);
  }

  return (
    <div>
      <form
        onSubmit={handleSubmit}
        className="flex gap-2 max-w-[420px] mx-auto flex-col sm:flex-row"
      >
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitted}
          placeholder="your@email.com"
          className={`flex-1 bg-surface border-[1.5px] rounded-full px-5 py-3 text-[13px] text-ink-100 outline-none transition-colors placeholder:text-ink-500 focus:border-accent ${
            error ? "border-accent" : "border-ink-700"
          }`}
          aria-label="Email address for waitlist"
        />
        <button
          type="submit"
          disabled={submitted}
          className={`font-sora text-[13px] font-semibold text-white border-none rounded-full px-7 py-3 cursor-pointer transition-all whitespace-nowrap ${
            submitted
              ? "bg-success shadow-none"
              : "bg-accent shadow-[0_4px_16px_rgba(196,105,79,0.22)] hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(196,105,79,0.32)]"
          }`}
        >
          {submitted ? "You're In" : "Join Waitlist"}
        </button>
      </form>
      <p
        className={`font-dm-mono text-[9px] tracking-[0.08em] mt-3.5 ${
          submitted ? "text-success" : "text-ink-500"
        }`}
      >
        {submitted
          ? "We'll reach out when your city goes live."
          : "No spam. Just a quiet email when it's ready."}
      </p>
    </div>
  );
}
