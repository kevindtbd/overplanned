"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { UserAvatar } from "@/components/shared/UserAvatar";

// ---------- Types ----------

interface TripChatProps {
  tripId: string;
  isOpen: boolean;
  onClose: () => void;
  currentUserId: string;
  /** Pre-attach a slot for sharing */
  sharedSlotRef?: {
    id: string;
    name: string;
    category: string;
    dayNumber: number;
  } | null;
  onClearSharedSlot?: () => void;
}

interface SlotRef {
  id: string;
  name: string;
  category: string;
  dayNumber: number;
  isStale?: boolean;
}

interface ChatMessage {
  id: string;
  userId: string;
  userName: string;
  avatarUrl?: string | null;
  body: string;
  slotRef?: SlotRef | null;
  createdAt: string;
  /** Marks optimistic messages not yet confirmed by the server */
  _pending?: boolean;
}

// ---------- Category Colors ----------

const CATEGORY_COLORS: Record<string, string> = {
  anchor: "bg-accent/15 text-accent",
  meal: "bg-warning-bg text-warning",
  flex: "bg-info-bg text-info",
  rest: "bg-success-bg text-success",
  transit: "bg-ink-800 text-ink-400",
};

function getCategoryClasses(category: string): string {
  return CATEGORY_COLORS[category.toLowerCase()] ?? "bg-ink-800 text-ink-400";
}

// ---------- Relative Time ----------

function relativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;

  if (diffMs < 0 || diffMs < 60_000) return "just now";

  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;

  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return "yesterday";

  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

// ---------- Slot Ref Card ----------

function SlotRefCard({
  slotRef,
  compact,
}: {
  slotRef: SlotRef;
  compact?: boolean;
}) {
  return (
    <div
      className={`
        mt-1.5 rounded-lg border border-ink-700 bg-base px-2.5 py-1.5
        cursor-pointer transition-colors hover:bg-surface
        ${slotRef.isStale ? "opacity-50" : ""}
        ${compact ? "max-w-[200px]" : ""}
      `}
      role="button"
      tabIndex={0}
      aria-label={`Activity: ${slotRef.name}, Day ${slotRef.dayNumber}`}
    >
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="font-sora text-[11px] font-medium text-ink-100 leading-tight truncate">
          {slotRef.name}
        </span>
        <span
          className={`
            inline-block font-dm-mono text-[9px] uppercase tracking-wider
            px-1.5 py-0.5 rounded
            ${getCategoryClasses(slotRef.category)}
          `}
        >
          {slotRef.category}
        </span>
        <span className="font-dm-mono text-[9px] text-ink-400">
          Day {slotRef.dayNumber}
        </span>
      </div>
      {slotRef.isStale && (
        <span className="font-dm-mono text-[9px] text-ink-500 mt-0.5 block">
          swapped
        </span>
      )}
    </div>
  );
}

// ---------- Shared Slot Preview (above input) ----------

function SharedSlotPreview({
  slot,
  onClear,
}: {
  slot: NonNullable<TripChatProps["sharedSlotRef"]>;
  onClear: () => void;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-ink-700 bg-surface/50">
      <div className="flex-1 min-w-0 flex items-center gap-1.5 flex-wrap">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-ink-400 shrink-0"
          aria-hidden="true"
        >
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
        </svg>
        <span className="font-sora text-[11px] font-medium text-ink-200 truncate">
          {slot.name}
        </span>
        <span
          className={`
            inline-block font-dm-mono text-[9px] uppercase tracking-wider
            px-1.5 py-0.5 rounded
            ${getCategoryClasses(slot.category)}
          `}
        >
          {slot.category}
        </span>
        <span className="font-dm-mono text-[9px] text-ink-400">
          Day {slot.dayNumber}
        </span>
      </div>
      <button
        onClick={onClear}
        className="shrink-0 p-0.5 rounded text-ink-400 hover:text-ink-200 transition-colors"
        aria-label="Remove attached activity"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

// ---------- Sending Dots ----------

function SendingDots() {
  return (
    <div className="flex items-center gap-1 px-2" aria-label="Sending">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-pulse"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

// ---------- Main Component ----------

const POLL_INTERVAL_MS = 30_000;
const ERROR_DISMISS_MS = 5_000;

export function TripChat({
  tripId,
  isOpen,
  onClose,
  currentUserId,
  sharedSlotRef,
  onClearSharedSlot,
}: TripChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-dismiss errors
  const showError = useCallback((msg: string) => {
    setError(msg);
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    errorTimerRef.current = setTimeout(() => setError(null), ERROR_DISMISS_MS);
  }, []);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, []);

  // Fetch messages
  const fetchMessages = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/trips/${tripId}/messages?limit=50`
      );
      if (!res.ok) throw new Error("Failed to load messages");
      const json = await res.json();
      const data: ChatMessage[] = json.messages ?? [];
      setMessages((prev) => {
        // Preserve any pending messages whose IDs haven't appeared in the server response
        const serverIds = new Set(data.map((m) => m.id));
        const stillPending = prev.filter(
          (m) => m._pending && !serverIds.has(m.id)
        );
        return [...data, ...stillPending];
      });
    } catch {
      // Silently fail on polls — only show error on initial load
    }
  }, [tripId]);

  // Initial fetch + polling
  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;

    async function init() {
      setLoading(true);
      try {
        const res = await fetch(
          `/api/trips/${tripId}/messages?limit=50`
        );
        if (!res.ok) throw new Error("Failed to load messages");
        if (cancelled) return;
        const json = await res.json();
        setMessages(json.messages ?? []);
        setTimeout(scrollToBottom, 50);
      } catch {
        if (!cancelled) showError("Could not load messages");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();

    const interval = setInterval(() => {
      if (!cancelled) fetchMessages().then(scrollToBottom);
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isOpen, tripId, fetchMessages, scrollToBottom, showError]);

  // Auto-scroll when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages.length, scrollToBottom]);

  // Auto-grow textarea
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
      const ta = e.target;
      ta.style.height = "auto";
      // Clamp to ~3 lines (approx 72px)
      ta.style.height = `${Math.min(ta.scrollHeight, 72)}px`;
    },
    []
  );

  // Send message
  const sendMessage = useCallback(async () => {
    const body = inputValue.trim();
    if (!body && !sharedSlotRef) return;

    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const optimistic: ChatMessage = {
      id: tempId,
      userId: currentUserId,
      userName: "You",
      body: body,
      slotRef: sharedSlotRef
        ? {
            id: sharedSlotRef.id,
            name: sharedSlotRef.name,
            category: sharedSlotRef.category,
            dayNumber: sharedSlotRef.dayNumber,
          }
        : null,
      createdAt: new Date().toISOString(),
      _pending: true,
    };

    setMessages((prev) => [...prev, optimistic]);
    setInputValue("");
    setSending(true);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    const slotRefId = sharedSlotRef?.id ?? undefined;
    if (sharedSlotRef && onClearSharedSlot) {
      onClearSharedSlot();
    }

    try {
      const res = await fetch(`/api/trips/${tripId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          body: body || undefined,
          slotRefId,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to send message");
      }

      const confirmed: ChatMessage = await res.json();

      // Replace optimistic message with confirmed one
      setMessages((prev) =>
        prev.map((m) => (m.id === tempId ? { ...confirmed, _pending: false } : m))
      );
    } catch (err) {
      // Remove the optimistic message on failure
      setMessages((prev) => prev.filter((m) => m.id !== tempId));
      showError(
        err instanceof Error ? err.message : "Could not send message"
      );
    } finally {
      setSending(false);
    }
  }, [
    inputValue,
    sharedSlotRef,
    currentUserId,
    tripId,
    onClearSharedSlot,
    showError,
  ]);

  // Keyboard handling: Enter to send, Shift+Enter for newline
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!sending) sendMessage();
      }
    },
    [sending, sendMessage]
  );

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  // Cleanup error timer
  useEffect(() => {
    return () => {
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    };
  }, []);

  const canSend = inputValue.trim().length > 0 || !!sharedSlotRef;

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop — visible on mobile only */}
      <div
        className="fixed inset-0 z-40 bg-black/40 sm:bg-transparent sm:pointer-events-none"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        className="
          fixed top-0 right-0 z-50 flex h-full flex-col
          w-full sm:w-[400px]
          bg-base border-l border-ink-700
          shadow-xl
          animate-slide-in-right
        "
        role="dialog"
        aria-label="Trip Chat"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-700 bg-surface/50">
          <h2 className="font-sora text-base font-semibold text-ink-100">
            Trip Chat
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-ink-400 hover:text-ink-200 hover:bg-surface transition-colors"
            aria-label="Close chat"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Message list */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
        >
          {loading && messages.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="flex items-center gap-2 text-ink-400">
                <SendingDots />
                <span className="font-dm-mono text-xs">Loading</span>
              </div>
            </div>
          )}

          {!loading && messages.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <p className="font-dm-mono text-sm text-ink-400 text-center">
                No messages yet. Start the conversation!
              </p>
            </div>
          )}

          {messages.map((msg) => {
            const isOwn = msg.userId === currentUserId;

            return (
              <div
                key={msg.id}
                className={`flex gap-2 ${isOwn ? "flex-row-reverse" : "flex-row"}`}
              >
                {/* Avatar */}
                {!isOwn && (
                  <UserAvatar name={msg.userName} avatarUrl={msg.avatarUrl} size="md" />
                )}

                {/* Bubble */}
                <div
                  className={`
                    max-w-[75%] min-w-0
                    ${isOwn ? "items-end" : "items-start"}
                  `}
                >
                  {/* Name + time */}
                  <div
                    className={`flex items-baseline gap-1.5 mb-0.5 ${
                      isOwn ? "flex-row-reverse" : "flex-row"
                    }`}
                  >
                    <span className="font-sora text-[11px] font-medium text-ink-200">
                      {isOwn ? "You" : msg.userName}
                    </span>
                    <span className="font-dm-mono text-[9px] text-ink-500">
                      {relativeTime(msg.createdAt)}
                    </span>
                  </div>

                  {/* Message body */}
                  {msg.body && (
                    <div
                      className={`
                        rounded-xl px-3 py-2
                        font-dm-mono text-[13px] leading-relaxed
                        ${msg._pending ? "opacity-70" : ""}
                        ${
                          isOwn
                            ? "bg-accent text-white rounded-tr-sm"
                            : "bg-surface text-ink-100 border border-ink-700 rounded-tl-sm"
                        }
                      `}
                    >
                      <p className="whitespace-pre-wrap break-words">
                        {msg.body}
                      </p>
                    </div>
                  )}

                  {/* Slot ref card */}
                  {msg.slotRef && <SlotRefCard slotRef={msg.slotRef} />}
                </div>
              </div>
            );
          })}
        </div>

        {/* Input area */}
        <div className="border-t border-ink-700">
          {/* Shared slot preview */}
          {sharedSlotRef && onClearSharedSlot && (
            <SharedSlotPreview
              slot={sharedSlotRef}
              onClear={onClearSharedSlot}
            />
          )}

          {/* Error message */}
          {error && (
            <div className="px-3 pt-2">
              <p className="font-dm-mono text-[11px] text-error">
                {error}
              </p>
            </div>
          )}

          {/* Text input row */}
          <div className="flex items-end gap-2 px-3 py-3">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="
                flex-1 resize-none
                rounded-xl border border-ink-700 bg-surface
                px-3 py-2
                font-dm-mono text-[13px] text-ink-100
                placeholder:text-ink-500
                focus:border-accent focus:outline-none
                transition-colors
              "
              style={{ maxHeight: 72 }}
              aria-label="Message input"
            />
            <button
              onClick={sendMessage}
              disabled={!canSend || sending}
              className="
                shrink-0 rounded-xl bg-accent p-2.5
                text-white transition-all
                hover:bg-accent/90
                disabled:opacity-40 disabled:cursor-not-allowed
              "
              aria-label="Send message"
            >
              {sending ? (
                <SendingDots />
              ) : (
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
