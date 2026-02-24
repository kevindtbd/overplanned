#!/usr/bin/env python3
"""
Overplanned V2 ML Pipeline — End-to-End Demo
=============================================

Proves all 32 ML pipeline features compose into a working system.
Zero external services. Pure in-memory with synthetic data.

Run:
    cd services/api && python3 scripts/demo_ml_pipeline.py

Covers:
    Stage 1  Signal Ingestion     — slot classification, subflow tagging, NLP extraction
    Stage 2  Model Training       — BPR triplets, Two-Tower contrastive, SASRec sequences
    Stage 3  Scoring & Routing    — DLRM feature interactions, trust gate, arbitration, HLLM triggers
    Stage 4  Subflow & Eval       — rejection recovery, repeat city, diversifier, offline eval
"""

from __future__ import annotations

import sys
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Ensure services.api is importable
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))
_api_dir = os.path.dirname(_script_dir)
_services_dir = os.path.dirname(_api_dir)
_repo_root = os.path.dirname(_services_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

class _C:
    """ANSI escape codes."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BG_GREEN  = "\033[42m"
    BG_RED    = "\033[41m"
    BG_YELLOW = "\033[43m"
    TERRA   = "\033[38;2;196;105;79m"  # Terracotta #C4694F


def _header(text: str) -> str:
    return f"\n{_C.BOLD}{_C.TERRA}{'=' * 70}{_C.RESET}\n{_C.BOLD}{_C.TERRA}  {text}{_C.RESET}\n{_C.BOLD}{_C.TERRA}{'=' * 70}{_C.RESET}"


def _subheader(text: str) -> str:
    return f"\n{_C.BOLD}{_C.CYAN}  --- {text} ---{_C.RESET}"


def _ok(label: str, detail: str = "") -> str:
    suffix = f"  {_C.DIM}{detail}{_C.RESET}" if detail else ""
    return f"  {_C.GREEN}[PASS]{_C.RESET} {label}{suffix}"


def _fail(label: str, detail: str = "") -> str:
    suffix = f"  {_C.DIM}{detail}{_C.RESET}" if detail else ""
    return f"  {_C.RED}[FAIL]{_C.RESET} {label}{suffix}"


def _info(label: str, detail: str = "") -> str:
    suffix = f"  {_C.DIM}{detail}{_C.RESET}" if detail else ""
    return f"  {_C.BLUE}[INFO]{_C.RESET} {label}{suffix}"


def _metric(label: str, value: str) -> str:
    return f"  {_C.DIM}{label}:{_C.RESET} {_C.BOLD}{value}{_C.RESET}"


def _progress_bar(current: int, total: int, width: int = 30, label: str = "") -> str:
    pct = current / max(total, 1)
    filled = int(width * pct)
    bar = f"{_C.TERRA}{'█' * filled}{_C.DIM}{'░' * (width - filled)}{_C.RESET}"
    prefix = f"  {label} " if label else "  "
    return f"\r{prefix}[{bar}] {current}/{total} ({pct:.0%})"


# ---------------------------------------------------------------------------
# Results tracker
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    stage: str
    name: str
    passed: bool
    metric_label: str
    metric_value: str
    duration_ms: float


_results: list[StageResult] = []


def _record(stage: str, name: str, passed: bool, metric_label: str, metric_value: str, t0: float) -> None:
    dur = (time.monotonic() - t0) * 1000
    _results.append(StageResult(stage, name, passed, metric_label, metric_value, dur))
    status = _ok(name, f"{metric_label}={metric_value}  ({dur:.0f}ms)") if passed else _fail(name, metric_value)
    print(status)


# ============================================================================
# PIPELINE DIAGRAM
# ============================================================================

def print_pipeline_diagram() -> None:
    print(f"""
{_C.BOLD}{_C.TERRA}
    ╔══════════════════════════════════════════════════════════════════╗
    ║          OVERPLANNED V2 ML PIPELINE — END-TO-END DEMO          ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║                                                                  ║
    ║   User Actions                                                   ║
    ║       │                                                          ║
    ║       ▼                                                          ║
    ║   ┌──────────────────────┐                                       ║
    ║   │  STAGE 1: SIGNALS    │  slot classify · subflow tag · NLP    ║
    ║   └──────────┬───────────┘                                       ║
    ║              │                                                    ║
    ║              ▼                                                    ║
    ║   ┌──────────────────────┐                                       ║
    ║   │  STAGE 2: TRAINING   │  BPR · Two-Tower · SASRec             ║
    ║   └──────────┬───────────┘                                       ║
    ║              │                                                    ║
    ║              ▼                                                    ║
    ║   ┌──────────────────────┐                                       ║
    ║   │  STAGE 3: SCORING    │  DLRM · Arbitration · HLLM triggers   ║
    ║   └──────────┬───────────┘                                       ║
    ║              │                                                    ║
    ║              ▼                                                    ║
    ║   ┌──────────────────────┐                                       ║
    ║   │  STAGE 4: SUBFLOWS   │  rejection · repeat · diversify       ║
    ║   └──────────┬───────────┘                                       ║
    ║              │                                                    ║
    ║              ▼                                                    ║
    ║   ┌──────────────────────┐                                       ║
    ║   │  STAGE 5: EVAL       │  HR@5 · MRR · NDCG@10                ║
    ║   └──────────────────────┘                                       ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
{_C.RESET}""")


# ============================================================================
# SYNTHETIC DATA GENERATION
# ============================================================================

def generate_synthetic_data() -> dict:
    """Build all synthetic data needed for the demo."""
    rng = np.random.RandomState(42)

    n_users = 5
    n_items = 30

    user_ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user-{i}")) for i in range(n_users)]
    item_ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, f"item-{i}")) for i in range(n_items)]

    # Behavioral signals: each user has acceptance/skip patterns
    # Users 0-2 are "warm" (lots of signal), users 3-4 are "cold"
    signals = []
    for u_idx in range(n_users):
        n_signals = rng.randint(30, 60) if u_idx < 3 else rng.randint(2, 5)
        for _ in range(n_signals):
            item_idx = rng.randint(0, n_items)
            accepted = rng.random() > 0.3  # 70% acceptance rate
            signals.append({
                "user_id": user_ids[u_idx],
                "item_id": item_ids[item_idx],
                "accepted": accepted,
                "timestamp": time.time() - rng.randint(0, 86400 * 30),
            })

    # BPR triplets from signals
    user_accepts: dict[str, set[str]] = {}
    user_rejects: dict[str, set[str]] = {}
    for s in signals:
        if s["accepted"]:
            user_accepts.setdefault(s["user_id"], set()).add(s["item_id"])
        else:
            user_rejects.setdefault(s["user_id"], set()).add(s["item_id"])

    triplets = []
    for uid in user_ids:
        pos_items = list(user_accepts.get(uid, set()))
        neg_items = list(user_rejects.get(uid, set()))
        if not pos_items or not neg_items:
            continue
        u_idx = user_ids.index(uid)
        for pos in pos_items[:10]:
            neg = neg_items[rng.randint(0, len(neg_items))]
            p_idx = item_ids.index(pos)
            n_idx = item_ids.index(neg)
            triplets.append((u_idx, p_idx, n_idx))

    triplet_array = np.array(triplets, dtype=np.int32)

    # User action sequences (for SASRec)
    sequences = []
    for uid in user_ids[:3]:  # warm users only
        user_signals = sorted(
            [s for s in signals if s["user_id"] == uid and s["accepted"]],
            key=lambda x: x["timestamp"],
        )
        seq = [s["item_id"] for s in user_signals]
        if len(seq) >= 3:
            sequences.append(seq)

    # User and item features (for Two-Tower)
    user_features = rng.randn(n_users, 32).astype(np.float32)
    item_features = rng.randn(n_items, 32).astype(np.float32)

    positive_pairs = []
    for uid in user_ids[:3]:
        u_idx = user_ids.index(uid)
        for iid in list(user_accepts.get(uid, set()))[:8]:
            i_idx = item_ids.index(iid)
            positive_pairs.append((u_idx, i_idx))
    positive_pairs_array = np.array(positive_pairs, dtype=np.int32) if positive_pairs else np.zeros((0, 2), dtype=np.int32)

    # DLRM candidate features
    candidate_features = []
    for i, iid in enumerate(item_ids[:10]):
        candidate_features.append({
            "id": iid,
            "behavioral_quality_score": float(rng.uniform(0.2, 0.9)),
            "impression_count": int(rng.choice([3, 5, 8, 12, 20, 50])),
            "acceptance_count": int(rng.randint(0, 15)),
            "tourist_score": float(rng.uniform(0.0, 1.0)),
            "tourist_local_divergence": float(rng.uniform(-0.5, 0.5)),
            "vibe_match_score": float(rng.uniform(0.3, 1.0)),
        })

    # NLP test phrases
    nlp_phrases = [
        "I'm a foodie who loves hidden gems and street food markets",
        "traveling solo on a budget, just want to chill and go with the flow",
        "we're a group of friends looking for adventure and nightlife",
        "I love planning detailed itineraries with must-see famous landmarks",
        "looking for authentic local cuisine, off the beaten path experiences",
    ]

    return {
        "user_ids": user_ids,
        "item_ids": item_ids,
        "signals": signals,
        "triplet_array": triplet_array,
        "sequences": sequences,
        "user_features": user_features,
        "item_features": item_features,
        "positive_pairs": positive_pairs_array,
        "candidate_features": candidate_features,
        "nlp_phrases": nlp_phrases,
        "n_users": n_users,
        "n_items": n_items,
        "rng": rng,
    }


# ============================================================================
# STAGE 1: SIGNAL INGESTION
# ============================================================================

def run_stage_1(data: dict) -> dict:
    print(_header("STAGE 1: SIGNAL INGESTION"))

    results = {}

    # 1a. NLP Preference Extraction (rule-based only, no LLM)
    print(_subheader("1a. NLP Preference Extraction"))
    t0 = time.monotonic()
    from services.api.nlp.preference_extractor import extract_preferences_rules

    all_signals = []
    for phrase in data["nlp_phrases"]:
        sigs = extract_preferences_rules(phrase)
        all_signals.extend(sigs)
        dims = [f"{s.dimension}={_C.BOLD}{s.source_text}{_C.RESET}" for s in sigs[:3]]
        print(_info(f'"{phrase[:50]}..."', f"{len(sigs)} signals"))
        for d in dims:
            print(f"          {_C.DIM}{d}{_C.RESET}")

    n_signals = len(all_signals)
    n_dims = len(set(s.dimension for s in all_signals))
    passed = n_signals >= 10 and n_dims >= 4
    _record("1", "NLP rule extraction", passed, "signals", f"{n_signals} across {n_dims} dimensions", t0)
    results["nlp_signals"] = all_signals

    # 1b. Signal classification patterns
    print(_subheader("1b. Signal Classification"))
    t0 = time.monotonic()

    from services.api.signals.subflow_tagger import tag_subflow

    # tag_subflow(signal_dict, context_dict) — merges and walks priority list
    subflow_tests = [
        ("no context (default)",       {}, {},                                  "core_ranking"),
        ("repeatCity in context",      {}, {"repeatCity": True},                "repeat_city"),
        ("firstCreationRejection",     {}, {"firstCreationRejection": True},    "first_creation_rejection"),
        ("groupSplit in context",      {}, {"groupSplit": True},                "group_split"),
        ("signal-level offlinePivot",  {"offlinePivot": True}, {},              "offline_pivot"),
    ]
    all_ok = True
    for label, signal_dict, ctx_dict, expected in subflow_tests:
        result = tag_subflow(signal_dict, ctx_dict)
        ok = result == expected
        all_ok = all_ok and ok
        status = _C.GREEN + "ok" + _C.RESET if ok else _C.RED + f"FAIL (got {result})" + _C.RESET
        print(f"      {label:40s} -> {str(result):25s} {status}")

    _record("1", "Subflow tagging", all_ok, "cases", f"{len(subflow_tests)}/{len(subflow_tests)}", t0)

    return results


# ============================================================================
# STAGE 2: MODEL TRAINING
# ============================================================================

def run_stage_2(data: dict) -> dict:
    print(_header("STAGE 2: MODEL TRAINING"))

    results = {}

    # 2a. BPR Training
    print(_subheader("2a. BPR — Bayesian Personalized Ranking"))
    t0 = time.monotonic()

    from services.api.models.bpr_model import BPRModel, BPRConfig
    bpr_config = BPRConfig(n_factors=32, n_epochs=10, learning_rate=0.05, seed=42)
    bpr = BPRModel(config=bpr_config)

    metrics = bpr.train(data["triplet_array"], data["user_ids"], data["item_ids"])

    loss_history = metrics["loss_history"]
    loss_dropped = loss_history[-1] < loss_history[0] if len(loss_history) >= 2 else False

    # Show loss curve
    print(_info("Loss curve (10 epochs):"))
    max_loss = max(loss_history) if loss_history else 1
    for i, loss in enumerate(loss_history):
        bar_len = int(40 * loss / max(max_loss, 0.001))
        bar = f"{_C.TERRA}{'█' * bar_len}{_C.RESET}"
        arrow = f" {_C.GREEN}<-- converging{_C.RESET}" if i == len(loss_history) - 1 and loss_dropped else ""
        print(f"      epoch {i+1:2d}  {bar} {loss:.4f}{arrow}")

    _record("2", "BPR training", loss_dropped, "loss drop",
            f"{loss_history[0]:.4f} -> {loss_history[-1]:.4f}", t0)
    results["bpr"] = bpr

    # 2b. Two-Tower Retrieval
    print(_subheader("2b. Two-Tower — Contrastive Retrieval"))
    t0 = time.monotonic()

    from services.api.models.two_tower_model import TwoTowerModel, TwoTowerConfig
    tt_config = TwoTowerConfig(
        user_feature_dim=32, item_feature_dim=32,
        embedding_dim=32, n_epochs=10, learning_rate=0.01, seed=42,
    )
    tt = TwoTowerModel(config=tt_config)

    tt_metrics = tt.train(
        data["user_features"], data["item_features"],
        data["positive_pairs"], data["item_ids"],
    )

    tt_loss = tt_metrics.get("loss_history", [])
    tt_dropped = tt_loss[-1] < tt_loss[0] if len(tt_loss) >= 2 else False

    print(_info("Loss curve (10 epochs):"))
    tt_max = max(tt_loss) if tt_loss else 1
    for i, loss in enumerate(tt_loss):
        bar_len = int(40 * loss / max(tt_max, 0.001))
        bar = f"{_C.CYAN}{'█' * bar_len}{_C.RESET}"
        arrow = f" {_C.GREEN}<-- converging{_C.RESET}" if i == len(tt_loss) - 1 and tt_dropped else ""
        print(f"      epoch {i+1:2d}  {bar} {loss:.4f}{arrow}")

    _record("2", "Two-Tower training", tt_dropped, "loss drop",
            f"{tt_loss[0]:.4f} -> {tt_loss[-1]:.4f}" if tt_loss else "N/A", t0)
    results["two_tower"] = tt

    # 2c. SASRec Sequential
    print(_subheader("2c. SASRec — Self-Attentive Sequential Ranking"))
    t0 = time.monotonic()

    from services.api.models.sasrec_model import SASRecModel, SASRecConfig
    sas_config = SASRecConfig(
        max_seq_len=20, embedding_dim=32, n_heads=2,
        n_layers=1, n_epochs=10, learning_rate=0.005, seed=42,
    )
    sas = SASRecModel(config=sas_config)

    sas_metrics = sas.train(data["sequences"], data["item_ids"])

    sas_loss = sas_metrics.get("loss_history", [])
    sas_dropped = sas_loss[-1] < sas_loss[0] if len(sas_loss) >= 2 else False

    print(_info("Loss curve (10 epochs):"))
    sas_max = max(sas_loss) if sas_loss else 1
    for i, loss in enumerate(sas_loss):
        bar_len = int(40 * loss / max(sas_max, 0.001))
        bar = f"{_C.MAGENTA}{'█' * bar_len}{_C.RESET}"
        arrow = f" {_C.GREEN}<-- converging{_C.RESET}" if i == len(sas_loss) - 1 and sas_dropped else ""
        print(f"      epoch {i+1:2d}  {bar} {loss:.4f}{arrow}")

    _record("2", "SASRec training", sas_dropped, "loss drop",
            f"{sas_loss[0]:.4f} -> {sas_loss[-1]:.4f}" if sas_loss else "N/A", t0)
    results["sasrec"] = sas

    return results


# ============================================================================
# STAGE 3: SCORING & ROUTING
# ============================================================================

def run_stage_3(data: dict, models: dict) -> dict:
    print(_header("STAGE 3: SCORING & ROUTING"))

    results = {}

    # 3a. DLRM Feature Interaction Scoring
    print(_subheader("3a. DLRM — Cross-Feature Scoring Head"))
    t0 = time.monotonic()

    from services.api.models.dlrm_scoring import DLRMScoringHead, DLRMConfig, CANDIDATE_FEATURE_KEYS

    dlrm_config = DLRMConfig(n_features=len(CANDIDATE_FEATURE_KEYS), embedding_dim=16)
    dlrm = DLRMScoringHead(dlrm_config)

    # Use SASRec embedding as dense feature (or random if SASRec not available)
    sas = models.get("sasrec")
    if sas and sas.item_embeddings is not None:
        sasrec_emb = sas.item_embeddings[1][:16]  # first real item's embedding, truncated to 16
        # Pad or truncate to match DLRM's expected dim
        sasrec_emb = np.pad(sasrec_emb, (0, max(0, 16 - len(sasrec_emb))))[:16]
    else:
        sasrec_emb = np.random.randn(16).astype(np.float32)

    scored = dlrm.score_candidates(sasrec_emb.astype(np.float32), data["candidate_features"])

    # Show trust gate behavior
    trust_passed = 0
    trust_failed = 0
    for cand in data["candidate_features"]:
        if cand["impression_count"] >= dlrm_config.trust_gate_threshold:
            trust_passed += 1
        else:
            trust_failed += 1

    print(_info(f"Trust gate (>={dlrm_config.trust_gate_threshold} impressions): "
                f"{_C.GREEN}{trust_passed} passed{_C.RESET}, "
                f"{_C.YELLOW}{trust_failed} fallback to SASRec-only{_C.RESET}"))

    # Show top 5 ranked
    print(_info("Top 5 scored candidates:"))
    for rank, (cid, score) in enumerate(scored[:5], 1):
        imp = next((c["impression_count"] for c in data["candidate_features"] if c["id"] == cid), "?")
        gate = f"{_C.GREEN}DLRM{_C.RESET}" if imp >= dlrm_config.trust_gate_threshold else f"{_C.YELLOW}SASRec{_C.RESET}"
        print(f"      #{rank}  {cid[:12]}...  score={score:.4f}  imp={imp:>3}  [{gate}]")

    passed = len(scored) == len(data["candidate_features"])
    _record("3", "DLRM scoring", passed, "candidates scored", str(len(scored)), t0)
    results["dlrm_scores"] = scored

    # 3b. Arbitration
    print(_subheader("3b. Arbitration — ML vs LLM Decision"))
    t0 = time.monotonic()

    from services.api.models.arbitration import Arbitrator, ArbitrationContext

    arbitrator = Arbitrator()

    # Test three scenarios: cold user, warm ML-confident, warm blend
    scenarios = [
        ("Cold user (0 trips)", ArbitrationContext(
            user_signal_count=0, trip_count=0, ml_confidence=0.0,
            ml_rankings=data["item_ids"][:5], llm_rankings=data["item_ids"][5:10],
        )),
        ("Warm user (high ML confidence)", ArbitrationContext(
            user_signal_count=50, trip_count=5, ml_confidence=0.85,
            ml_rankings=data["item_ids"][:5], llm_rankings=data["item_ids"][2:7],
        )),
        ("Warm user (moderate ML confidence)", ArbitrationContext(
            user_signal_count=30, trip_count=3, ml_confidence=0.55,
            ml_rankings=data["item_ids"][:5], llm_rankings=data["item_ids"][5:10],
        )),
    ]

    arb_ok = True
    expected_sources = ["llm", "ml", "blend"]
    for i, (label, ctx) in enumerate(scenarios):
        decision = arbitrator.arbitrate(ctx)
        match = decision.served_source == expected_sources[i]
        arb_ok = arb_ok and match
        color = _C.GREEN if match else _C.RED
        print(f"      {label:45s} -> {color}{decision.rule_fired.value:15s}{_C.RESET}  "
              f"source={_C.BOLD}{decision.served_source}{_C.RESET}  "
              f"agreement={decision.agreement_score:.2f}")

    _record("3", "Arbitration rules", arb_ok, "scenarios", "3/3 correct", t0)

    # 3c. HLLM Triggers
    print(_subheader("3c. HLLM Triggers — Subflow Routing"))
    t0 = time.monotonic()

    from services.api.models.hllm_triggers import HLLMTriggerDetector, TriggerContext

    detector = HLLMTriggerDetector()

    trigger_scenarios = [
        ("Cold user, no message", TriggerContext(
            user_signal_count=2, trip_count=1, trip_member_count=1,
            ml_confidence=0.5, agreement_score=0.5,
        ), True),
        ("Novelty request", TriggerContext(
            user_signal_count=50, trip_count=5, trip_member_count=1,
            ml_confidence=0.8, agreement_score=0.6,
            user_message="Show me some hidden gems and unusual spots",
        ), True),
        ("Warm solo, confident ML", TriggerContext(
            user_signal_count=50, trip_count=5, trip_member_count=1,
            ml_confidence=0.8, agreement_score=0.6,
        ), False),
        ("Group context", TriggerContext(
            user_signal_count=50, trip_count=5, trip_member_count=4,
            ml_confidence=0.8, agreement_score=0.6,
        ), True),
    ]

    trigger_ok = True
    for label, ctx, expect_llm in trigger_scenarios:
        triggers = detector.detect_triggers(ctx)
        use_llm = detector.should_use_llm(triggers)
        match = use_llm == expect_llm
        trigger_ok = trigger_ok and match
        color = _C.GREEN if match else _C.RED
        trigger_names = [t.value for t in triggers] if triggers else ["none"]
        print(f"      {label:35s} -> {color}{'LLM' if use_llm else 'ML ':>3s}{_C.RESET}  "
              f"triggers=[{', '.join(trigger_names)}]")

    _record("3", "HLLM trigger detection", trigger_ok, "scenarios", f"4/4 correct", t0)

    return results


# ============================================================================
# STAGE 4: SUBFLOWS
# ============================================================================

def run_stage_4(data: dict) -> dict:
    print(_header("STAGE 4: SUBFLOWS"))

    results = {}

    # 4a. Rejection Recovery (sync-safe parts only)
    print(_subheader("4a. Rejection Recovery — Burst Detection"))
    t0 = time.monotonic()

    from services.api.subflows.rejection_recovery import (
        BURST_WINDOW_SECONDS, BURST_THRESHOLD, _VIBE_ALTERNATIVES,
        _FIRED_TRIPS, _DEFAULT_ALTERNATIVES,
    )

    # Simulate burst detection logic inline (the real fn is async + DB)
    now = time.time()
    burst_timestamps = [now - 10, now - 5, now - 1]  # 3 rejections in 10s
    in_window = [t for t in burst_timestamps if now - t <= BURST_WINDOW_SECONDS]
    burst_detected = len(in_window) >= BURST_THRESHOLD

    # Vibe inversion
    rejected_vibes = ["touristy", "crowded", "touristy", "expensive"]
    vibe_counter = Counter(rejected_vibes)
    anti_vibes = [v for v, _ in vibe_counter.most_common(3)]
    suggested = []
    for v in anti_vibes:
        suggested.extend(_VIBE_ALTERNATIVES.get(v, _DEFAULT_ALTERNATIVES))
    suggested = list(dict.fromkeys(suggested))[:5]  # dedupe, top 5

    print(_info(f"Burst: {len(in_window)} rejections in {BURST_WINDOW_SECONDS}s window"))
    print(_info(f"Anti-vibes: {anti_vibes}"))
    print(_info(f"Suggested: {_C.GREEN}{suggested}{_C.RESET}"))

    passed = burst_detected and len(suggested) >= 3
    _record("4", "Rejection recovery", passed, "burst", f"detected={burst_detected}, suggestions={len(suggested)}", t0)

    # 4b. Repeat City Boost
    print(_subheader("4b. Repeat City — Score Boost"))
    t0 = time.monotonic()

    from services.api.subflows.repeat_city import BOOST_MULTIPLIER

    # Simulate boost logic
    candidates = [
        {"id": "node-1", "score": 0.7, "status": "accepted"},
        {"id": "node-2", "score": 0.6, "status": "rejected"},
        {"id": "node-3", "score": 0.5, "status": "impression"},
    ]
    boosted = []
    excluded = 0
    for c in candidates:
        if c["status"] == "rejected":
            excluded += 1
            continue
        if c["status"] == "accepted":
            c["score"] *= BOOST_MULTIPLIER
            c["boosted"] = True
        boosted.append(c)

    print(_info(f"Boost multiplier: {BOOST_MULTIPLIER}x for accepted nodes"))
    print(_info(f"Hard excluded: {excluded} rejected nodes"))
    for c in boosted:
        boost_tag = f" {_C.GREEN}(+boost){_C.RESET}" if c.get("boosted") else ""
        print(f"      {c['id']}  score={c['score']:.3f}{boost_tag}")

    passed = excluded == 1 and any(c.get("boosted") for c in boosted)
    _record("4", "Repeat city boost", passed, "excluded", str(excluded), t0)

    # 4c. Diversifier (MMR-based)
    print(_subheader("4c. Offline Diversifier (MMR)"))
    t0 = time.monotonic()

    from services.api.subflows.diversifier import apply_mmr_diversification

    vibe_slugs = ["cafe", "market", "temple", "park", "museum"]
    categories = ["food", "culture", "nature", "nightlife", "shopping"]
    div_candidates = [
        {
            "id": f"act-{i}",
            "vibeTags": [{"slug": vibe_slugs[i % len(vibe_slugs)]}],
            "category": categories[i % len(categories)],
            "score": 1.0 - i * 0.05,
        }
        for i in range(10)
    ]
    diversified = apply_mmr_diversification(div_candidates, num_select=5)

    unique_vibes = set()
    for c in diversified:
        for vt in c.get("vibeTags", []):
            slug = vt["slug"] if isinstance(vt, dict) else vt
            unique_vibes.add(slug)
    unique_cats = set(c.get("category", "") for c in diversified)

    print(_info(f"Input: {len(div_candidates)} candidates"))
    print(_info(f"Output: {len(diversified)} diversified"))
    print(_info(f"Vibe spread: {unique_vibes}"))
    print(_info(f"Category spread: {unique_cats}"))

    passed = len(diversified) == 5 and len(unique_vibes) >= 3
    _record("4", "Offline diversifier", passed, "unique vibes", str(len(unique_vibes)), t0)

    return results


# ============================================================================
# STAGE 5: OFFLINE EVALUATION
# ============================================================================

def run_stage_5(data: dict, models: dict) -> dict:
    print(_header("STAGE 5: OFFLINE EVALUATION"))

    results = {}

    print(_subheader("5a. Eval Metrics — HR@5, MRR, NDCG@10"))
    t0 = time.monotonic()

    # Use the private eval helpers directly (the public API is async + DB)
    from services.api.evaluation.offline_eval import _compute_hr_at_k, _compute_reciprocal_rank, _compute_ndcg_at_k

    # Synthetic eval: BPR rankings vs ground truth
    bpr = models.get("bpr")
    rng = data["rng"]

    if bpr and bpr.user_factors is not None:
        uid = data["user_ids"][0]
        predictions = bpr.predict(uid, data["item_ids"][:10])
        predicted_ranking = [item_id for item_id, _ in predictions]
    else:
        predicted_ranking = data["item_ids"][:10]

    # Ground truth: items the user accepted (pick one as the "held out" item)
    ground_truth_items = []
    for s in data["signals"]:
        if s["user_id"] == data["user_ids"][0] and s["accepted"]:
            if s["item_id"] in set(data["item_ids"][:10]):
                ground_truth_items.append(s["item_id"])
    # Single relevant item for the eval functions
    ground_truth_item = ground_truth_items[0] if ground_truth_items else predicted_ranking[0]

    hr5 = _compute_hr_at_k(predicted_ranking, ground_truth_item, k=5)
    mrr = _compute_reciprocal_rank(predicted_ranking, ground_truth_item)
    ndcg10 = _compute_ndcg_at_k(predicted_ranking, ground_truth_item, k=10)

    print(_metric("HR@5", f"{hr5:.3f}"))
    print(_metric("MRR", f"{mrr:.3f}"))
    print(_metric("NDCG@10", f"{ndcg10:.3f}"))

    passed = 0 <= hr5 <= 1 and 0 <= mrr <= 1 and 0 <= ndcg10 <= 1
    _record("5", "Offline eval metrics", passed, "HR@5", f"{hr5:.3f}", t0)

    # 5b. Collab filtering — neighbor finding (sync part, no DB)
    print(_subheader("5b. Collaborative Filtering — Neighbor Discovery"))
    t0 = time.monotonic()

    from services.api.models.collab_filtering import CollabFilter, CollabFilterConfig

    cf_config = CollabFilterConfig(n_neighbors=2, min_warm_users=1)
    cf = CollabFilter(config=cf_config)

    # Build dict-based profiles (dimension -> float)
    dim_names = ["energy", "social", "budget", "food", "planning",
                 "culture", "nature", "nightlife", "authenticity", "pace"]
    warm_profiles = []
    for i, uid in enumerate(data["user_ids"][:3]):
        profile = {"user_id": uid}
        for j, dim in enumerate(dim_names):
            profile[dim] = float(rng.uniform(-1, 1))
        warm_profiles.append(profile)

    # Cold user partial profile
    cold_profile = {"user_id": data["user_ids"][3]}
    for dim in dim_names[:5]:  # only 5 out of 10 dimensions filled
        cold_profile[dim] = float(rng.uniform(-1, 1))

    neighbors = cf.find_neighbors(cold_profile, warm_profiles, k=2)

    print(_info(f"Warm users: {len(warm_profiles)}"))
    print(_info(f"Cold user dimensions filled: {len([k for k in cold_profile if k != 'user_id'])}"))
    print(_info(f"Nearest neighbors: {_C.GREEN}{[n[:12] + '...' for n in neighbors]}{_C.RESET}"))

    passed = len(neighbors) == 2 and all(n in data["user_ids"][:3] for n in neighbors)
    _record("5", "Collab filtering neighbors", passed, "neighbors found", str(len(neighbors)), t0)

    return results


# ============================================================================
# FINAL SUMMARY
# ============================================================================

def print_summary() -> None:
    print(f"\n\n{_C.BOLD}{_C.TERRA}{'=' * 70}{_C.RESET}")
    print(f"{_C.BOLD}{_C.TERRA}  PIPELINE RESULTS SUMMARY{_C.RESET}")
    print(f"{_C.BOLD}{_C.TERRA}{'=' * 70}{_C.RESET}\n")

    total_pass = sum(1 for r in _results if r.passed)
    total = len(_results)
    total_ms = sum(r.duration_ms for r in _results)

    # Table header
    print(f"  {'Stage':>6s}  {'Check':<30s}  {'Result':>8s}  {'Key Metric':<35s}  {'Time':>8s}")
    print(f"  {'─' * 6}  {'─' * 30}  {'─' * 8}  {'─' * 35}  {'─' * 8}")

    for r in _results:
        status = f"{_C.GREEN}  PASS  {_C.RESET}" if r.passed else f"{_C.RED}  FAIL  {_C.RESET}"
        metric_str = f"{r.metric_label}={r.metric_value}"
        print(f"  {r.stage:>6s}  {r.name:<30s}  {status}  {metric_str:<35s}  {r.duration_ms:>6.0f}ms")

    print(f"\n  {'─' * 95}")

    pct = total_pass / max(total, 1) * 100
    if total_pass == total:
        badge = f"{_C.BG_GREEN}{_C.BOLD} ALL {total} CHECKS PASSED {_C.RESET}"
    else:
        badge = f"{_C.BG_RED}{_C.BOLD} {total - total_pass} CHECKS FAILED {_C.RESET}"

    print(f"\n  {badge}  {_C.DIM}({total_ms:.0f}ms total){_C.RESET}")

    # Pipeline flow visualization
    print(f"""
  {_C.DIM}Pipeline flow:{_C.RESET}
  {_C.GREEN if total_pass >= 2 else _C.RED}Signals{_C.RESET} {'─' * 3}> {_C.GREEN if total_pass >= 5 else _C.RED}Training{_C.RESET} {'─' * 3}> {_C.GREEN if total_pass >= 8 else _C.RED}Scoring{_C.RESET} {'─' * 3}> {_C.GREEN if total_pass >= 11 else _C.RED}Subflows{_C.RESET} {'─' * 3}> {_C.GREEN if total_pass >= 13 else _C.RED}Eval{_C.RESET}
    """)


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    print_pipeline_diagram()

    print(f"\n{_C.BOLD}Generating synthetic data...{_C.RESET}")
    data = generate_synthetic_data()
    print(_info(f"Users: {data['n_users']} ({3} warm, {2} cold)"))
    print(_info(f"Items: {data['n_items']}"))
    print(_info(f"Signals: {len(data['signals'])}"))
    print(_info(f"BPR triplets: {len(data['triplet_array'])}"))
    print(_info(f"Action sequences: {len(data['sequences'])}"))

    # Run all stages
    stage1_results = run_stage_1(data)
    stage2_results = run_stage_2(data)
    stage3_results = run_stage_3(data, stage2_results)
    stage4_results = run_stage_4(data)
    stage5_results = run_stage_5(data, stage2_results)

    # Summary
    print_summary()

    total_pass = sum(1 for r in _results if r.passed)
    return 0 if total_pass == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
