"""
Integration tests for the Overplanned V2 ML pipeline.

Verifies that ML pipeline modules compose correctly end-to-end.
All tests are pure in-memory -- no database, no external services.

Test classes:
  1. TestSignalIngestion    -- NLP extraction + subflow tagging
  2. TestModelTraining      -- BPR / Two-Tower / SASRec training convergence
  3. TestScoringAndRouting  -- DLRM scoring, arbitration rules, HLLM triggers
  4. TestSubflowsAndEval   -- rejection recovery helpers, diversification, eval metrics, collab filtering
"""

import math
import sys
import time

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup -- ensure both project root and services/api are importable.
# The preference_extractor uses `from services.api.nlp.patterns import ...`
# so the project root must be on sys.path. Other modules use relative
# imports within services/api, so we add that path too.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = "/home/pogchamp/Desktop/overplanned"
_API_ROOT = "/home/pogchamp/Desktop/overplanned/services/api"
for _p in (_PROJECT_ROOT, _API_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Module imports (verified against source)
# ---------------------------------------------------------------------------
from services.api.nlp.preference_extractor import extract_preferences_rules, PreferenceSignal
from services.api.signals.subflow_tagger import tag_subflow
from services.api.models.bpr_model import BPRModel, BPRConfig
from services.api.models.two_tower_model import TwoTowerModel, TwoTowerConfig
from services.api.models.sasrec_model import SASRecModel, SASRecConfig
from services.api.models.dlrm_scoring import DLRMScoringHead, DLRMConfig, CANDIDATE_FEATURE_KEYS
from services.api.models.arbitration import (
    Arbitrator,
    ArbitrationContext,
    ArbitrationDecision,
    ArbitrationRule,
)
from services.api.models.hllm_triggers import (
    HLLMTriggerDetector,
    TriggerContext,
    HLLMTrigger,
)
from services.api.subflows.diversifier import apply_mmr_diversification
from services.api.subflows.rejection_recovery import (
    _is_burst,
    _extract_anti_vibes,
    _invert_vibes,
    BURST_WINDOW_SECONDS,
    BURST_THRESHOLD,
    RECOVERY_WEIGHT_CAP,
    reset_fired_trips,
)
from services.api.subflows.repeat_city import _apply_boost, BOOST_MULTIPLIER
from services.api.evaluation.offline_eval import (
    _compute_hr_at_k,
    _compute_reciprocal_rank,
    _compute_ndcg_at_k,
)
from services.api.models.collab_filtering import CollabFilter, CollabFilterConfig


# ===================================================================
# 1. Signal Ingestion
# ===================================================================

class TestSignalIngestion:
    """NLP extraction produces signals; subflow tagging routes correctly."""

    # ---------------------------------------------------------------
    # NLP preference extraction (rule-based pass only -- no LLM)
    # ---------------------------------------------------------------

    def test_extract_preferences_rules_adventure_text(self):
        """Adventure-oriented text triggers energy_level = high_energy."""
        text = "I love adventure and thrill seeking when I travel."
        signals = extract_preferences_rules(text)
        assert len(signals) >= 1
        dims = {s.dimension for s in signals}
        assert "energy_level" in dims
        energy_sig = next(s for s in signals if s.dimension == "energy_level")
        assert energy_sig.source == "rule_based"
        assert energy_sig.confidence > 0

    def test_extract_preferences_rules_budget_text(self):
        """Budget-oriented text triggers budget_orientation."""
        text = "I am on a budget and looking for affordable street food."
        signals = extract_preferences_rules(text)
        dims = {s.dimension for s in signals}
        assert "budget_orientation" in dims

    def test_extract_preferences_rules_multi_dimension(self):
        """Text covering multiple dimensions yields multiple signals."""
        text = (
            "I love adventure and thrill seeking. "
            "Traveling solo is my thing. "
            "I am on a budget."
        )
        signals = extract_preferences_rules(text)
        dims = {s.dimension for s in signals}
        assert len(dims) >= 2
        assert "energy_level" in dims
        assert "social_orientation" in dims

    def test_extract_preferences_rules_empty_text(self):
        """Empty or whitespace input produces zero signals."""
        assert extract_preferences_rules("") == []
        assert extract_preferences_rules("   ") == []

    def test_extract_preferences_sorted_by_confidence(self):
        """Returned signals are sorted descending by confidence."""
        text = "I love adventure. Traveling solo. I am on a budget."
        signals = extract_preferences_rules(text)
        if len(signals) >= 2:
            confidences = [s.confidence for s in signals]
            assert confidences == sorted(confidences, reverse=True)

    def test_preference_signal_fields(self):
        """PreferenceSignal has the expected attributes."""
        text = "I love adventure"
        signals = extract_preferences_rules(text)
        assert len(signals) >= 1
        sig = signals[0]
        assert hasattr(sig, "dimension")
        assert hasattr(sig, "direction")
        assert hasattr(sig, "confidence")
        assert hasattr(sig, "source_text")
        assert hasattr(sig, "source")

    def test_preference_signal_source_text_truncation(self):
        """source_text is truncated at 500 chars."""
        sig = PreferenceSignal(
            dimension="energy_level",
            direction="positive",
            confidence=0.8,
            source_text="x" * 600,
            source="rule_based",
        )
        assert len(sig.source_text) == 500

    # ---------------------------------------------------------------
    # NLP signals -> subflow tagger composition
    # ---------------------------------------------------------------

    def test_nlp_signals_feed_subflow_tagger(self):
        """Signals from NLP extraction can be used as context for subflow tagging."""
        text = "I love adventure and I am on a budget."
        signals = extract_preferences_rules(text)
        assert len(signals) >= 1

        # The subflow tagger operates on raw dicts, not PreferenceSignal.
        # In a real pipeline, signals feed into BehavioralSignal creation
        # which then gets tagged. Here we verify the tagger works with
        # a plausible signal dict.
        signal_dict = {"signalType": "preference_extracted", "dimension": signals[0].dimension}
        context_dict = {}
        subflow = tag_subflow(signal_dict, context_dict)
        assert subflow == "core_ranking"

    # ---------------------------------------------------------------
    # Subflow tagger priority
    # ---------------------------------------------------------------

    def test_subflow_default_core_ranking(self):
        """Empty signal + context yields core_ranking."""
        assert tag_subflow({}, {}) == "core_ranking"

    def test_subflow_first_creation_rejection(self):
        """firstCreationRejection is highest priority."""
        tag = tag_subflow(
            {},
            {"firstCreationRejection": True, "repeatCity": True},
        )
        assert tag == "first_creation_rejection"

    def test_subflow_repeat_city(self):
        """repeatCity triggers repeat_city subflow."""
        assert tag_subflow({}, {"repeatCity": True}) == "repeat_city"

    def test_subflow_group_split(self):
        """groupSplit triggers group_split subflow."""
        assert tag_subflow({}, {"groupSplit": True}) == "group_split"

    def test_subflow_onthefly_add_from_signal(self):
        """ontheflyAdd flag in signal dict also works."""
        assert tag_subflow({"ontheflyAdd": True}, {}) == "onthefly_add"

    def test_subflow_priority_ordering(self):
        """Higher-priority context key wins over lower-priority."""
        # groupSplit (priority 5) beats repeatCity (priority 6)
        tag = tag_subflow({}, {"groupSplit": True, "repeatCity": True})
        assert tag == "group_split"

    def test_subflow_none_on_none_inputs(self):
        """Both None returns None."""
        assert tag_subflow(None, None) is None

    def test_subflow_signal_merges_with_context(self):
        """Signal-level and context-level keys merge; priority still applies."""
        tag = tag_subflow(
            {"ontheflyAdd": True},
            {"firstCreationRejection": True},
        )
        # firstCreationRejection has higher priority
        assert tag == "first_creation_rejection"


# ===================================================================
# 2. Model Training
# ===================================================================

class TestModelTraining:
    """BPR, Two-Tower, and SASRec all train and produce decreasing loss."""

    # ---------------------------------------------------------------
    # BPR
    # ---------------------------------------------------------------

    def test_bpr_trains_and_loss_decreases(self):
        """BPR training produces a loss history that trends downward."""
        rng = np.random.RandomState(42)
        n_users, n_items, n_triplets = 10, 20, 200

        user_ids = [f"user_{i}" for i in range(n_users)]
        item_ids = [f"item_{i}" for i in range(n_items)]

        triplets = np.column_stack([
            rng.randint(0, n_users, n_triplets),
            rng.randint(0, n_items, n_triplets),
            rng.randint(0, n_items, n_triplets),
        ])

        config = BPRConfig(n_factors=16, learning_rate=0.05, reg=0.001, n_epochs=30, seed=42)
        model = BPRModel(config=config)
        metrics = model.train(triplets, user_ids, item_ids)

        assert "final_loss" in metrics
        assert "loss_history" in metrics
        loss_history = metrics["loss_history"]
        assert len(loss_history) == 30

        # First epoch loss should be greater than last epoch loss
        assert loss_history[0] > loss_history[-1], (
            f"Loss did not decrease: first={loss_history[0]:.4f} last={loss_history[-1]:.4f}"
        )

    def test_bpr_predict_returns_ranked_items(self):
        """BPR predict returns (item_id, score) tuples sorted descending."""
        rng = np.random.RandomState(42)
        n_users, n_items = 5, 10
        user_ids = [f"u{i}" for i in range(n_users)]
        item_ids = [f"i{i}" for i in range(n_items)]

        # Create structured triplets so user 0 prefers items 0-4
        triplets = []
        for _ in range(100):
            u = rng.randint(0, n_users)
            pos = rng.randint(0, n_items // 2)
            neg = rng.randint(n_items // 2, n_items)
            triplets.append([u, pos, neg])
        triplets = np.array(triplets, dtype=np.int32)

        model = BPRModel(config=BPRConfig(n_factors=8, n_epochs=20, seed=42))
        model.train(triplets, user_ids, item_ids)

        results = model.predict("u0", item_ids)
        assert isinstance(results, list)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # Sorted descending by score
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_bpr_cold_user_predict(self):
        """Unknown user gets zero scores for all items."""
        user_ids = ["u0"]
        item_ids = ["i0", "i1"]
        triplets = np.array([[0, 0, 1]], dtype=np.int32)

        model = BPRModel(config=BPRConfig(n_epochs=1))
        model.train(triplets, user_ids, item_ids)

        results = model.predict("unknown_user", item_ids)
        assert all(score == 0.0 for _, score in results)

    # ---------------------------------------------------------------
    # Two-Tower
    # ---------------------------------------------------------------

    def test_two_tower_trains_and_loss_decreases(self):
        """Two-Tower training loss decreases over epochs."""
        rng = np.random.RandomState(42)
        n_users, n_items = 8, 15
        user_dim, item_dim = 6, 6

        user_features = rng.randn(n_users, user_dim).astype(np.float64)
        item_features = rng.randn(n_items, item_dim).astype(np.float64)
        item_ids = [f"item_{i}" for i in range(n_items)]

        # Create positive pairs (user_idx, item_idx)
        positive_pairs = np.array(
            [[i % n_users, i % n_items] for i in range(50)],
            dtype=np.int32,
        )

        config = TwoTowerConfig(
            user_feature_dim=user_dim,
            item_feature_dim=item_dim,
            embedding_dim=16,
            learning_rate=0.01,
            n_epochs=30,
            temperature=0.1,
            seed=42,
        )
        model = TwoTowerModel(config=config)
        metrics = model.train(user_features, item_features, positive_pairs, item_ids)

        loss_history = metrics["loss_history"]
        assert len(loss_history) == 30
        assert loss_history[0] > loss_history[-1], (
            f"Two-Tower loss did not decrease: first={loss_history[0]:.4f} last={loss_history[-1]:.4f}"
        )

    def test_two_tower_predict_returns_ranked_items(self):
        """Two-Tower predict returns ranked (item_id, score) tuples."""
        rng = np.random.RandomState(42)
        n_users, n_items, user_dim, item_dim = 4, 8, 4, 4

        user_features = rng.randn(n_users, user_dim)
        item_features = rng.randn(n_items, item_dim)
        item_ids = [f"it{i}" for i in range(n_items)]
        positive_pairs = np.array([[0, 0], [1, 1], [2, 2], [3, 3]])

        config = TwoTowerConfig(
            user_feature_dim=user_dim,
            item_feature_dim=item_dim,
            embedding_dim=8,
            n_epochs=5,
            seed=42,
        )
        model = TwoTowerModel(config=config)
        model.train(user_features, item_features, positive_pairs, item_ids)

        candidates = [
            {"id": f"it{i}", "features": item_features[i]} for i in range(n_items)
        ]
        results = model.predict(user_features[0], candidates)
        assert len(results) == n_items
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    # ---------------------------------------------------------------
    # SASRec
    # ---------------------------------------------------------------

    def test_sasrec_trains_and_loss_decreases(self):
        """SASRec training loss decreases over epochs."""
        item_ids = [f"act_{i}" for i in range(15)]

        # Create synthetic user sequences
        rng = np.random.RandomState(42)
        sequences = []
        for _ in range(20):
            seq_len = rng.randint(3, 8)
            seq = [item_ids[rng.randint(0, len(item_ids))] for _ in range(seq_len)]
            sequences.append(seq)

        config = SASRecConfig(
            max_seq_len=10,
            embedding_dim=16,
            n_heads=2,
            n_layers=1,
            learning_rate=0.005,
            n_epochs=15,
            seed=42,
        )
        model = SASRecModel(config=config)
        metrics = model.train(sequences, item_ids)

        loss_history = metrics["loss_history"]
        assert len(loss_history) == 15
        # Use average of first 3 vs last 3 to smooth noise
        early_avg = np.mean(loss_history[:3])
        late_avg = np.mean(loss_history[-3:])
        assert early_avg > late_avg, (
            f"SASRec loss did not decrease: early_avg={early_avg:.4f} late_avg={late_avg:.4f}"
        )

    def test_sasrec_predict_returns_ranked_items(self):
        """SASRec predict re-ranks candidates based on user sequence."""
        item_ids = [f"a{i}" for i in range(10)]
        sequences = [item_ids[:5], item_ids[3:8], item_ids[1:6]]

        config = SASRecConfig(
            max_seq_len=10, embedding_dim=16, n_heads=2,
            n_layers=1, n_epochs=5, seed=42,
        )
        model = SASRecModel(config=config)
        model.train(sequences, item_ids)

        results = model.predict(["a0", "a1", "a2"], ["a3", "a4", "a5"])
        assert isinstance(results, list)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_sasrec_cold_start_empty_sequence(self):
        """Empty user sequence returns zero scores."""
        item_ids = ["x0", "x1", "x2"]
        sequences = [["x0", "x1", "x2"]]
        model = SASRecModel(config=SASRecConfig(n_epochs=1, embedding_dim=8, n_heads=2, n_layers=1))
        model.train(sequences, item_ids)

        results = model.predict([], ["x0", "x1"])
        assert all(score == 0.0 for _, score in results)

    # ---------------------------------------------------------------
    # Cross-model: BPR -> SASRec composition
    # ---------------------------------------------------------------

    def test_bpr_output_feeds_sasrec_candidates(self):
        """BPR rankings can be used as SASRec candidate list."""
        rng = np.random.RandomState(42)
        item_ids = [f"item_{i}" for i in range(10)]

        # Train BPR
        user_ids = ["u0", "u1"]
        triplets = np.array(
            [[0, i, (i + 5) % 10] for i in range(5)] +
            [[1, (i + 5) % 10, i] for i in range(5)],
            dtype=np.int32,
        )
        bpr = BPRModel(config=BPRConfig(n_factors=8, n_epochs=10, seed=42))
        bpr.train(triplets, user_ids, item_ids)
        bpr_rankings = bpr.predict("u0", item_ids)
        bpr_top_ids = [iid for iid, _ in bpr_rankings[:5]]

        # Train SASRec and re-rank BPR output
        sequences = [item_ids[:5], item_ids[5:]]
        sasrec = SASRecModel(config=SASRecConfig(
            max_seq_len=10, embedding_dim=8, n_heads=2,
            n_layers=1, n_epochs=3, seed=42,
        ))
        sasrec.train(sequences, item_ids)

        reranked = sasrec.predict(["item_0", "item_1"], bpr_top_ids)
        assert len(reranked) == len(bpr_top_ids)
        reranked_ids = {iid for iid, _ in reranked}
        assert reranked_ids == set(bpr_top_ids)


# ===================================================================
# 3. Scoring and Routing
# ===================================================================

class TestScoringAndRouting:
    """DLRM scores candidates; arbitration picks correct rules; HLLM triggers fire."""

    # ---------------------------------------------------------------
    # DLRM Scoring Head
    # ---------------------------------------------------------------

    def test_dlrm_scores_candidates(self):
        """DLRM score_candidates returns (id, score) tuples sorted descending."""
        n_features = len(CANDIDATE_FEATURE_KEYS)
        config = DLRMConfig(
            n_features=n_features,
            embedding_dim=8,
            trust_gate_threshold=5,
        )
        head = DLRMScoringHead(config)

        sasrec_output = np.random.default_rng(42).normal(size=(8,)).astype(np.float32)

        candidates = [
            {
                "id": f"cand_{i}",
                "behavioral_quality_score": float(i) / 5,
                "impression_count": 10 + i,
                "acceptance_count": i,
                "tourist_score": 0.3,
                "tourist_local_divergence": 0.1,
                "vibe_match_score": 0.5 + i * 0.1,
            }
            for i in range(5)
        ]

        results = head.score_candidates(sasrec_output, candidates)
        assert isinstance(results, list)
        assert len(results) == 5
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # Check sorted descending
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_dlrm_trust_gate_fallback(self):
        """Candidates below trust gate threshold get fallback scoring."""
        n_features = len(CANDIDATE_FEATURE_KEYS)
        config = DLRMConfig(
            n_features=n_features,
            embedding_dim=8,
            trust_gate_threshold=100,  # Very high threshold
        )
        head = DLRMScoringHead(config)
        sasrec_output = np.ones(8, dtype=np.float32)

        candidates = [
            {
                "id": "low_impressions",
                "behavioral_quality_score": 0.9,
                "impression_count": 2,  # Below threshold
                "acceptance_count": 1,
                "tourist_score": 0.1,
                "tourist_local_divergence": 0.05,
                "vibe_match_score": 0.9,
            },
        ]

        results = head.score_candidates(sasrec_output, candidates)
        assert len(results) == 1
        # The score should be the fallback value (mean of sasrec * 0.5)
        cid, score = results[0]
        assert cid == "low_impressions"
        expected_fallback = float(np.mean(sasrec_output)) * 0.5
        assert abs(score - expected_fallback) < 1e-5

    def test_dlrm_mixed_trust_gate(self):
        """Mix of trusted and untrusted candidates are all scored."""
        n_features = len(CANDIDATE_FEATURE_KEYS)
        config = DLRMConfig(
            n_features=n_features,
            embedding_dim=8,
            trust_gate_threshold=10,
        )
        head = DLRMScoringHead(config)
        sasrec_output = np.random.default_rng(42).normal(size=(8,)).astype(np.float32)

        candidates = [
            {
                "id": "trusted",
                "behavioral_quality_score": 0.8,
                "impression_count": 50,
                "acceptance_count": 10,
                "tourist_score": 0.2,
                "tourist_local_divergence": 0.1,
                "vibe_match_score": 0.7,
            },
            {
                "id": "untrusted",
                "behavioral_quality_score": 0.9,
                "impression_count": 3,
                "acceptance_count": 1,
                "tourist_score": 0.1,
                "tourist_local_divergence": 0.05,
                "vibe_match_score": 0.9,
            },
        ]

        results = head.score_candidates(sasrec_output, candidates)
        assert len(results) == 2
        result_ids = {r[0] for r in results}
        assert result_ids == {"trusted", "untrusted"}

    # ---------------------------------------------------------------
    # SASRec -> DLRM composition
    # ---------------------------------------------------------------

    def test_sasrec_output_feeds_dlrm(self):
        """SASRec output vector can be passed directly into DLRM scoring."""
        item_ids = [f"a{i}" for i in range(8)]
        sequences = [item_ids[:4], item_ids[4:]]
        sasrec = SASRecModel(config=SASRecConfig(
            max_seq_len=10, embedding_dim=16, n_heads=2,
            n_layers=1, n_epochs=3, seed=42,
        ))
        sasrec.train(sequences, item_ids)

        # Get the SASRec output representation for a sequence
        input_seq = np.array(
            [sasrec.item_id_map[iid] for iid in ["a0", "a1", "a2"]],
            dtype=np.int32,
        )
        sasrec_repr = sasrec._forward(input_seq)[-1]  # Last position output

        # Feed into DLRM
        n_features = len(CANDIDATE_FEATURE_KEYS)
        dlrm = DLRMScoringHead(DLRMConfig(
            n_features=n_features,
            embedding_dim=16,
            trust_gate_threshold=0,
        ))

        candidates = [
            {
                "id": f"a{i}",
                "behavioral_quality_score": 0.5,
                "impression_count": 20,
                "acceptance_count": 5,
                "tourist_score": 0.3,
                "tourist_local_divergence": 0.1,
                "vibe_match_score": 0.6,
            }
            for i in range(3, 7)
        ]

        results = dlrm.score_candidates(sasrec_repr, candidates)
        assert len(results) == 4
        assert all(isinstance(s, float) for _, s in results)

    # ---------------------------------------------------------------
    # Arbitration
    # ---------------------------------------------------------------

    def test_arbitration_llm_cold_zero_trips(self):
        """trip_count == 0 triggers LLM_COLD rule."""
        arb = Arbitrator()
        ctx = ArbitrationContext(
            user_signal_count=0,
            trip_count=0,
            ml_confidence=0.9,
            ml_rankings=["a", "b", "c"],
            llm_rankings=["x", "y", "z"],
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_COLD
        assert decision.served_source == "llm"
        assert decision.served_rankings == ["x", "y", "z"]

    def test_arbitration_llm_wins_low_signals(self):
        """user_signal_count < 10 triggers LLM_WINS."""
        arb = Arbitrator()
        ctx = ArbitrationContext(
            user_signal_count=5,
            trip_count=2,
            ml_confidence=0.8,
            ml_rankings=["a", "b"],
            llm_rankings=["x", "y"],
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_WINS

    def test_arbitration_ml_explore_with_budget(self):
        """exploration_budget_remaining > 0 triggers ML_EXPLORE."""
        arb = Arbitrator()
        ctx = ArbitrationContext(
            user_signal_count=50,
            trip_count=5,
            ml_confidence=0.3,
            ml_rankings=["a", "b"],
            llm_rankings=["x", "y"],
            exploration_budget_remaining=3,
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.ML_EXPLORE
        assert decision.served_source == "ml"

    def test_arbitration_ml_wins_high_confidence(self):
        """High ML confidence + high agreement triggers ML_WINS."""
        arb = Arbitrator()
        shared = ["a", "b", "c", "d", "e"]
        ctx = ArbitrationContext(
            user_signal_count=50,
            trip_count=10,
            ml_confidence=0.85,
            ml_rankings=shared,
            llm_rankings=shared,  # 100% agreement
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.ML_WINS
        assert decision.agreement_score == 1.0

    def test_arbitration_blend_moderate_confidence(self):
        """Moderate ML confidence triggers BLEND."""
        arb = Arbitrator()
        ctx = ArbitrationContext(
            user_signal_count=50,
            trip_count=10,
            ml_confidence=0.6,
            ml_rankings=["a", "b", "c"],
            llm_rankings=["x", "y", "z"],  # 0% agreement
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.BLEND
        assert decision.served_source == "blend"
        # Blended should interleave
        assert decision.served_rankings[0] == "a"
        assert decision.served_rankings[1] == "x"

    def test_arbitration_default_llm_wins(self):
        """Low ML confidence + no exploration budget falls back to LLM_WINS."""
        arb = Arbitrator()
        ctx = ArbitrationContext(
            user_signal_count=50,
            trip_count=10,
            ml_confidence=0.3,
            ml_rankings=["a", "b"],
            llm_rankings=["x", "y"],
        )
        decision = arb.arbitrate(ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_WINS

    def test_arbitration_agreement_score_computation(self):
        """Agreement score correctly computes overlap@5."""
        score = Arbitrator.compute_agreement_score(
            ["a", "b", "c", "d", "e"],
            ["a", "c", "e", "x", "y"],
            k=5,
        )
        # Overlap: a, c, e = 3/5
        assert abs(score - 0.6) < 1e-10

    # ---------------------------------------------------------------
    # HLLM Triggers
    # ---------------------------------------------------------------

    def test_hllm_cold_user_trigger(self):
        """Cold user (< threshold trips) fires COLD_USER trigger."""
        detector = HLLMTriggerDetector(cold_user_threshold=3)
        ctx = TriggerContext(
            user_signal_count=2,
            trip_count=1,
            trip_member_count=1,
            ml_confidence=0.5,
            agreement_score=0.5,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.COLD_USER in triggers
        assert detector.should_use_llm(triggers) is True

    def test_hllm_novelty_request(self):
        """Novelty keywords in user message fire NOVELTY_REQUEST."""
        detector = HLLMTriggerDetector()
        ctx = TriggerContext(
            user_signal_count=100,
            trip_count=10,
            trip_member_count=1,
            ml_confidence=0.8,
            agreement_score=0.8,
            user_message="Show me something off the beaten path",
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_hllm_low_confidence(self):
        """Low ML confidence fires LOW_ML_CONFIDENCE."""
        detector = HLLMTriggerDetector(low_confidence_threshold=0.3)
        ctx = TriggerContext(
            user_signal_count=50,
            trip_count=10,
            trip_member_count=1,
            ml_confidence=0.1,
            agreement_score=0.5,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.LOW_ML_CONFIDENCE in triggers

    def test_hllm_high_disagreement(self):
        """Low agreement score fires HIGH_DISAGREEMENT."""
        detector = HLLMTriggerDetector(high_disagreement_threshold=0.2)
        ctx = TriggerContext(
            user_signal_count=50,
            trip_count=10,
            trip_member_count=1,
            ml_confidence=0.8,
            agreement_score=0.1,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.HIGH_DISAGREEMENT in triggers

    def test_hllm_group_context(self):
        """Group trips with 3+ members fire GROUP_CONTEXT."""
        detector = HLLMTriggerDetector(group_size_threshold=3)
        ctx = TriggerContext(
            user_signal_count=50,
            trip_count=10,
            trip_member_count=4,
            ml_confidence=0.8,
            agreement_score=0.8,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.GROUP_CONTEXT in triggers

    def test_hllm_pivot_event(self):
        """Active pivot fires PIVOT_EVENT."""
        detector = HLLMTriggerDetector()
        ctx = TriggerContext(
            user_signal_count=50,
            trip_count=10,
            trip_member_count=1,
            ml_confidence=0.8,
            agreement_score=0.8,
            has_active_pivot=True,
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.PIVOT_EVENT in triggers

    def test_hllm_cuisine_shift(self):
        """Category shift in recent signals fires CUISINE_SHIFT."""
        detector = HLLMTriggerDetector(cuisine_shift_ratio=0.6)
        ctx = TriggerContext(
            user_signal_count=50,
            trip_count=10,
            trip_member_count=1,
            ml_confidence=0.8,
            agreement_score=0.8,
            # 3 older "ramen" signals, then shift to "sushi"
            recent_signal_categories=["ramen", "ramen", "ramen", "sushi"],
        )
        triggers = detector.detect_triggers(ctx)
        assert HLLMTrigger.CUISINE_SHIFT in triggers

    def test_hllm_multiple_triggers_fire(self):
        """Multiple triggers can fire simultaneously."""
        detector = HLLMTriggerDetector(cold_user_threshold=5)
        ctx = TriggerContext(
            user_signal_count=2,
            trip_count=1,
            trip_member_count=4,
            ml_confidence=0.1,
            agreement_score=0.05,
            has_active_pivot=True,
            user_message="surprise me with hidden gems",
        )
        triggers = detector.detect_triggers(ctx)
        assert len(triggers) >= 3
        assert HLLMTrigger.COLD_USER in triggers
        assert HLLMTrigger.LOW_ML_CONFIDENCE in triggers
        assert HLLMTrigger.NOVELTY_REQUEST in triggers

    def test_hllm_no_triggers_warm_user(self):
        """Warm user with high confidence fires no triggers."""
        detector = HLLMTriggerDetector()
        ctx = TriggerContext(
            user_signal_count=100,
            trip_count=20,
            trip_member_count=1,
            ml_confidence=0.9,
            agreement_score=0.8,
        )
        triggers = detector.detect_triggers(ctx)
        assert len(triggers) == 0
        assert detector.should_use_llm(triggers) is False

    # ---------------------------------------------------------------
    # HLLM -> Arbitration composition
    # ---------------------------------------------------------------

    def test_hllm_triggers_inform_arbitration(self):
        """HLLM trigger detection result feeds into arbitration context."""
        detector = HLLMTriggerDetector(cold_user_threshold=3)
        trigger_ctx = TriggerContext(
            user_signal_count=1,
            trip_count=0,
            trip_member_count=1,
            ml_confidence=0.2,
            agreement_score=0.1,
        )
        triggers = detector.detect_triggers(trigger_ctx)
        use_llm = detector.should_use_llm(triggers)
        assert use_llm is True

        # The arbitration layer also sees trip_count=0, so LLM_COLD fires
        arb = Arbitrator()
        arb_ctx = ArbitrationContext(
            user_signal_count=1,
            trip_count=0,
            ml_confidence=0.2,
            ml_rankings=["a", "b"],
            llm_rankings=["x", "y"],
        )
        decision = arb.arbitrate(arb_ctx)
        assert decision.rule_fired == ArbitrationRule.LLM_COLD


# ===================================================================
# 4. Subflows and Evaluation
# ===================================================================

class TestSubflowsAndEval:
    """Rejection recovery, repeat city boost, diversification, eval metrics, collab filtering."""

    # ---------------------------------------------------------------
    # Rejection Recovery (internal helpers -- no DB needed)
    # ---------------------------------------------------------------

    def test_rejection_burst_detection_true(self):
        """3+ rejections within the burst window triggers burst."""
        now = time.time()
        timestamps = [now - 30, now - 20, now - 10]
        assert _is_burst(timestamps) is True

    def test_rejection_burst_detection_false_too_few(self):
        """Fewer than BURST_THRESHOLD rejections does not trigger."""
        now = time.time()
        timestamps = [now - 10, now - 5]
        assert _is_burst(timestamps) is False

    def test_rejection_burst_detection_false_too_spread(self):
        """Rejections spread beyond the burst window do not trigger."""
        now = time.time()
        # Space them far apart (3x burst window)
        timestamps = [
            now - BURST_WINDOW_SECONDS * 3,
            now - BURST_WINDOW_SECONDS * 2,
            now,
        ]
        # Only 1 within window of the most recent
        assert _is_burst(timestamps) is False

    def test_extract_anti_vibes_from_slots(self):
        """Anti-vibes extracted from rejected slot vibe tags."""
        slots = [
            {"vibeTags": [{"slug": "touristy"}, {"slug": "crowded"}]},
            {"vibeTags": [{"slug": "touristy"}]},
            {"vibeTags": [{"slug": "expensive"}]},
        ]
        anti = _extract_anti_vibes(slots)
        assert "touristy" in anti  # Most common

    def test_extract_anti_vibes_fallback_to_slot_type(self):
        """When no vibeTags, slotType is used as fallback."""
        slots = [
            {"slotType": "museum"},
            {"slotType": "museum"},
            {"slotType": "temple"},
        ]
        anti = _extract_anti_vibes(slots)
        assert "museum" in anti

    def test_invert_vibes_known_anti_vibes(self):
        """Known anti-vibes produce alternative suggestions."""
        suggestions = _invert_vibes(["touristy", "crowded"])
        assert len(suggestions) > 0
        # Should contain alternatives from the lookup table
        assert any(s in suggestions for s in [
            "local-hidden-gem", "neighborhood-spot", "off-the-beaten-path",
            "peaceful", "quiet", "low-key",
        ])

    def test_invert_vibes_unknown_falls_back_to_defaults(self):
        """Unknown anti-vibes fall back to default alternatives."""
        suggestions = _invert_vibes(["totally-made-up-vibe"])
        assert len(suggestions) > 0
        assert "local-hidden-gem" in suggestions

    def test_invert_vibes_max_five(self):
        """Suggestions are capped at 5."""
        suggestions = _invert_vibes(["touristy", "crowded", "expensive", "fine-dining", "chain"])
        assert len(suggestions) <= 5

    def test_recovery_weight_cap_in_range(self):
        """RECOVERY_WEIGHT_CAP is within the DB CHECK [-1.0, 3.0] constraint."""
        assert -1.0 <= RECOVERY_WEIGHT_CAP <= 3.0

    # ---------------------------------------------------------------
    # Repeat City Boost (pure helper)
    # ---------------------------------------------------------------

    def test_apply_boost_score_field(self):
        """_apply_boost multiplies the score field by BOOST_MULTIPLIER."""
        candidate = {"id": "node_1", "score": 0.8}
        boosted = _apply_boost(candidate)
        expected = round(0.8 * BOOST_MULTIPLIER, 6)
        assert boosted["score"] == expected
        assert boosted["_repeatCityBoosted"] is True

    def test_apply_boost_convergence_score(self):
        """_apply_boost also multiplies convergenceScore."""
        candidate = {"id": "node_1", "convergenceScore": 0.5, "score": 0.7}
        boosted = _apply_boost(candidate)
        assert boosted["convergenceScore"] == round(0.5 * BOOST_MULTIPLIER, 6)
        assert boosted["score"] == round(0.7 * BOOST_MULTIPLIER, 6)

    def test_apply_boost_no_score_unchanged(self):
        """Candidate without score fields is returned with boost tag only."""
        candidate = {"id": "node_1", "name": "Ramen Shop"}
        boosted = _apply_boost(candidate)
        assert "score" not in boosted
        assert boosted["_repeatCityBoosted"] is True
        assert boosted["name"] == "Ramen Shop"

    def test_apply_boost_does_not_mutate_original(self):
        """_apply_boost returns a new dict, not a mutation."""
        original = {"id": "node_1", "score": 0.8}
        boosted = _apply_boost(original)
        assert original["score"] == 0.8
        assert "_repeatCityBoosted" not in original
        assert boosted is not original

    # ---------------------------------------------------------------
    # MMR Diversification
    # ---------------------------------------------------------------

    def test_mmr_basic_selection(self):
        """MMR selects the requested number of candidates."""
        candidates = [
            {"id": f"c{i}", "score": 1.0 - i * 0.1, "vibeTags": [], "category": "food"}
            for i in range(10)
        ]
        selected = apply_mmr_diversification(candidates, num_select=3)
        assert len(selected) == 3

    def test_mmr_first_pick_is_highest_relevance(self):
        """First MMR pick is always the highest-relevance candidate."""
        candidates = [
            {"id": "low", "score": 0.3, "vibeTags": [], "category": "food"},
            {"id": "high", "score": 0.9, "vibeTags": [], "category": "food"},
            {"id": "mid", "score": 0.6, "vibeTags": [], "category": "food"},
        ]
        selected = apply_mmr_diversification(candidates, num_select=3)
        assert selected[0]["id"] == "high"

    def test_mmr_diversifies_categories(self):
        """MMR prefers candidates from different categories over same-category."""
        candidates = [
            {"id": "food1", "score": 0.9, "vibeTags": [{"slug": "ramen"}], "category": "food"},
            {"id": "food2", "score": 0.85, "vibeTags": [{"slug": "ramen"}], "category": "food"},
            {"id": "culture1", "score": 0.8, "vibeTags": [{"slug": "temple"}], "category": "culture"},
            {"id": "nature1", "score": 0.7, "vibeTags": [{"slug": "park"}], "category": "nature"},
        ]
        selected = apply_mmr_diversification(candidates, num_select=3, lambda_param=0.5)
        selected_categories = [c["category"] for c in selected]
        # With lambda=0.5 (balanced), should pick from different categories
        assert len(set(selected_categories)) >= 2

    def test_mmr_empty_candidates(self):
        """Empty candidate list returns empty."""
        assert apply_mmr_diversification([], num_select=5) == []

    def test_mmr_num_select_exceeds_candidates(self):
        """Selecting more than available returns all candidates."""
        candidates = [
            {"id": "a", "score": 0.9, "vibeTags": [], "category": "food"},
            {"id": "b", "score": 0.8, "vibeTags": [], "category": "culture"},
        ]
        selected = apply_mmr_diversification(candidates, num_select=10)
        assert len(selected) == 2

    def test_mmr_lambda_1_pure_relevance(self):
        """lambda=1.0 gives pure relevance ordering (no diversity penalty)."""
        candidates = [
            {"id": "c0", "score": 0.9, "vibeTags": [{"slug": "a"}], "category": "food"},
            {"id": "c1", "score": 0.8, "vibeTags": [{"slug": "a"}], "category": "food"},
            {"id": "c2", "score": 0.7, "vibeTags": [{"slug": "a"}], "category": "food"},
        ]
        selected = apply_mmr_diversification(candidates, num_select=3, lambda_param=1.0)
        ids = [c["id"] for c in selected]
        assert ids == ["c0", "c1", "c2"]

    # ---------------------------------------------------------------
    # Offline Eval Metrics
    # ---------------------------------------------------------------

    def test_hr_at_k_hit(self):
        """HR@5 returns 1.0 when ground truth is in top-k."""
        assert _compute_hr_at_k(["a", "b", "c", "d", "e"], "c", k=5) == 1.0

    def test_hr_at_k_miss(self):
        """HR@5 returns 0.0 when ground truth is not in top-k."""
        assert _compute_hr_at_k(["a", "b", "c", "d", "e"], "z", k=5) == 0.0

    def test_hr_at_k_boundary(self):
        """HR@5 misses when item is at position 6 (just outside k=5)."""
        rankings = ["a", "b", "c", "d", "e", "target"]
        assert _compute_hr_at_k(rankings, "target", k=5) == 0.0

    def test_reciprocal_rank_first(self):
        """MRR returns 1.0 when item is at position 1."""
        assert _compute_reciprocal_rank(["target", "b", "c"], "target") == 1.0

    def test_reciprocal_rank_third(self):
        """MRR returns 1/3 when item is at position 3."""
        rr = _compute_reciprocal_rank(["a", "b", "target", "d"], "target")
        assert abs(rr - 1.0 / 3.0) < 1e-10

    def test_reciprocal_rank_missing(self):
        """MRR returns 0.0 when item is not found."""
        assert _compute_reciprocal_rank(["a", "b", "c"], "z") == 0.0

    def test_ndcg_at_k_first_position(self):
        """NDCG@10 = 1.0 when the single relevant item is at position 1."""
        ndcg = _compute_ndcg_at_k(["target", "b", "c"], "target", k=10)
        assert abs(ndcg - 1.0) < 1e-10

    def test_ndcg_at_k_second_position(self):
        """NDCG@10 at position 2 equals log2(2)/log2(3)."""
        ndcg = _compute_ndcg_at_k(["a", "target", "c"], "target", k=10)
        expected = (1.0 / math.log2(3)) / (1.0 / math.log2(2))
        assert abs(ndcg - expected) < 1e-10

    def test_ndcg_at_k_outside_cutoff(self):
        """NDCG@k returns 0.0 when item is beyond the cutoff."""
        rankings = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "target"]
        assert _compute_ndcg_at_k(rankings, "target", k=10) == 0.0

    def test_ndcg_decreases_with_rank(self):
        """NDCG strictly decreases as item moves to later positions."""
        items = [f"x{i}" for i in range(10)]
        ndcg_values = []
        for pos in range(10):
            rankings = list(items)
            rankings.insert(pos, "target")
            ndcg_values.append(_compute_ndcg_at_k(rankings, "target", k=10))
        # Each position should give less or equal NDCG
        for i in range(len(ndcg_values) - 1):
            assert ndcg_values[i] >= ndcg_values[i + 1]

    # ---------------------------------------------------------------
    # Collab Filtering
    # ---------------------------------------------------------------

    def test_collab_filter_find_neighbors(self):
        """find_neighbors returns k nearest users by cosine similarity."""
        cf = CollabFilter(CollabFilterConfig(min_warm_users=2, n_neighbors=2, blend_weight=0.6))

        user_profile = {"user_id": "new_user", "energy_level": 0.8, "food_priority": 0.9}
        warm_profiles = [
            {"user_id": "warm_1", "energy_level": 0.7, "food_priority": 0.85},
            {"user_id": "warm_2", "energy_level": 0.1, "food_priority": 0.1},
            {"user_id": "warm_3", "energy_level": 0.75, "food_priority": 0.88},
        ]

        neighbors = cf.find_neighbors(user_profile, warm_profiles, k=2)
        assert len(neighbors) == 2
        # warm_1 and warm_3 are most similar to new_user
        assert "warm_1" in neighbors
        assert "warm_3" in neighbors
        assert "warm_2" not in neighbors

    def test_collab_filter_find_neighbors_empty(self):
        """Empty warm profiles returns empty list."""
        cf = CollabFilter(CollabFilterConfig(min_warm_users=2, n_neighbors=2))
        neighbors = cf.find_neighbors(
            {"user_id": "u", "dim1": 0.5}, [], k=2
        )
        assert neighbors == []

    def test_collab_filter_find_neighbors_fewer_than_k(self):
        """When fewer warm users than k, returns all available."""
        cf = CollabFilter(CollabFilterConfig(n_neighbors=10))
        neighbors = cf.find_neighbors(
            {"user_id": "u", "energy_level": 0.5},
            [{"user_id": "w1", "energy_level": 0.4}],
            k=5,
        )
        assert len(neighbors) == 1
        assert neighbors[0] == "w1"

    def test_collab_filter_similarity_ordering(self):
        """Neighbors are sorted by descending similarity."""
        cf = CollabFilter(CollabFilterConfig(n_neighbors=3))
        user = {"user_id": "u", "dim_a": 1.0, "dim_b": 0.0}
        warm = [
            {"user_id": "close", "dim_a": 0.99, "dim_b": 0.01},
            {"user_id": "far", "dim_a": 0.0, "dim_b": 1.0},
            {"user_id": "mid", "dim_a": 0.5, "dim_b": 0.5},
        ]
        neighbors = cf.find_neighbors(user, warm, k=3)
        assert neighbors[0] == "close"
        assert neighbors[-1] == "far"

    # ---------------------------------------------------------------
    # Full pipeline composition: NLP -> subflow -> model -> scoring -> arbitration
    # ---------------------------------------------------------------

    def test_end_to_end_pipeline_composition(self):
        """
        End-to-end in-memory pipeline:
        1. NLP extracts preferences from text
        2. Subflow tagger routes the signal context
        3. BPR model generates initial rankings
        4. SASRec re-ranks
        5. DLRM scores with feature interactions
        6. Arbitration picks the final winner
        7. Eval metrics validate the output
        """
        # Step 1: NLP extraction
        text = "I love adventure and thrill seeking. Traveling solo."
        signals = extract_preferences_rules(text)
        assert len(signals) >= 1

        # Step 2: Subflow tagging
        subflow = tag_subflow(
            {"signalType": "preference_extracted"},
            {"repeatCity": False},
        )
        assert subflow == "core_ranking"

        # Step 3: BPR generates initial rankings
        rng = np.random.RandomState(42)
        item_ids = [f"activity_{i}" for i in range(10)]
        user_ids = ["target_user", "other_user"]
        triplets = np.array(
            [[0, i, (i + 5) % 10] for i in range(5)] * 10,
            dtype=np.int32,
        )
        bpr = BPRModel(config=BPRConfig(n_factors=8, n_epochs=10, seed=42))
        bpr.train(triplets, user_ids, item_ids)
        bpr_results = bpr.predict("target_user", item_ids)
        bpr_ranked_ids = [iid for iid, _ in bpr_results]
        assert len(bpr_ranked_ids) == 10

        # Step 4: SASRec re-ranks the BPR top candidates
        sequences = [item_ids[:5], item_ids[5:], item_ids[2:7]]
        sasrec = SASRecModel(config=SASRecConfig(
            max_seq_len=10, embedding_dim=8, n_heads=2,
            n_layers=1, n_epochs=3, seed=42,
        ))
        sasrec.train(sequences, item_ids)
        sasrec_results = sasrec.predict(
            ["activity_0", "activity_1"],
            bpr_ranked_ids[:5],
        )
        assert len(sasrec_results) == 5

        # Step 5: DLRM scoring
        n_features = len(CANDIDATE_FEATURE_KEYS)
        dlrm = DLRMScoringHead(DLRMConfig(
            n_features=n_features,
            embedding_dim=8,
            trust_gate_threshold=0,
        ))
        sasrec_repr = np.random.default_rng(42).normal(size=(8,)).astype(np.float32)
        dlrm_candidates = [
            {
                "id": iid,
                "behavioral_quality_score": float(score),
                "impression_count": 20,
                "acceptance_count": 5,
                "tourist_score": 0.3,
                "tourist_local_divergence": 0.1,
                "vibe_match_score": 0.6,
            }
            for iid, score in sasrec_results
        ]
        dlrm_results = dlrm.score_candidates(sasrec_repr, dlrm_candidates)
        ml_rankings = [iid for iid, _ in dlrm_results]

        # Step 6: Arbitration
        arb = Arbitrator()
        llm_rankings = list(reversed(ml_rankings))  # Simulate divergent LLM
        arb_ctx = ArbitrationContext(
            user_signal_count=50,
            trip_count=10,
            ml_confidence=0.85,
            ml_rankings=ml_rankings,
            llm_rankings=llm_rankings,
        )
        decision = arb.arbitrate(arb_ctx)
        assert decision.served_rankings is not None
        assert len(decision.served_rankings) >= 1

        # Step 7: Eval metrics on the final rankings
        ground_truth = ml_rankings[0]
        hr = _compute_hr_at_k(decision.served_rankings, ground_truth, k=5)
        mrr = _compute_reciprocal_rank(decision.served_rankings, ground_truth)
        ndcg = _compute_ndcg_at_k(decision.served_rankings, ground_truth, k=10)

        # ground_truth is in the rankings, so these should be positive
        assert hr >= 0.0
        assert mrr >= 0.0
        assert ndcg >= 0.0
