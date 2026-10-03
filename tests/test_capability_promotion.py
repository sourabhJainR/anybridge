from anybridge.capability_promotion import (
    CanaryEvidence,
    CapabilityPromotionStore,
    CohortEvidence,
    HoldoutEvidence,
)


def test_independent_holdout_opens_canary():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 3, 0.95, 0.9))
    assert decision.action == "run_canary"
    assert decision.state.status == "canary"


def test_non_independent_holdout_cannot_promote():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 10, 1.0, 1.0, independent=False))
    assert decision.state.status == "candidate"


def test_canary_promotes_after_bounded_evidence():
    store = CapabilityPromotionStore()
    store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.95))
    decision = store.evaluate_canary(
        "cap", [CanaryEvidence("cap", True), CanaryEvidence("cap", True), CanaryEvidence("cap", True)]
    )
    assert decision.state.status == "promoted"
    assert decision.state.version == 1


def test_canary_regression_rolls_back_and_versions():
    store = CapabilityPromotionStore()
    store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.95))
    decision = store.evaluate_canary("cap", [CanaryEvidence("cap", False)])
    assert decision.state.status == "rolled_back"
    assert decision.action == "quarantine"
    assert decision.state.version == 1


def test_confidence_gate_keeps_capability_in_candidate_state():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.79))
    assert decision.state.status == "candidate"
    assert decision.action == "collect_holdout"


def test_canary_cannot_bypass_holdout_gate():
    store = CapabilityPromotionStore()
    decision = store.evaluate_canary("cap", [CanaryEvidence("cap", True)])
    assert decision.state.status == "candidate"
    assert decision.action == "collect_holdout"


def test_multi_cohort_requires_distinct_independence():
    store = CapabilityPromotionStore(min_cohorts=2)
    decision = store.evaluate_multi_cohort([
        CohortEvidence("cap", "a", True, 1.0, "domain", "family", "same"),
        CohortEvidence("cap", "b", True, 1.0, "domain", "family", "same"),
    ])
    assert decision.state.status == "candidate"


def test_multi_cohort_opens_canary_only_when_each_cohort_is_strong():
    store = CapabilityPromotionStore(min_cohorts=2)
    decision = store.evaluate_multi_cohort([
        CohortEvidence("cap", "a", True, 1.0, "domain-a", "family-a", "a"),
        CohortEvidence("cap", "b", True, 1.0, "domain-b", "family-b", "b"),
    ])
    assert decision.state.status == "canary"


def test_weak_independent_cohort_blocks_multi_cohort_promotion():
    store = CapabilityPromotionStore(min_cohorts=2)
    decision = store.evaluate_multi_cohort([
        CohortEvidence("cap", "a", True, 1.0, "domain-a", "family-a", "a"),
        CohortEvidence("cap", "b", False, 1.0, "domain-b", "family-b", "b"),
    ])
    assert decision.state.status == "candidate"


def test_repeated_post_promotion_decay_retires_capability():
    store = CapabilityPromotionStore(min_cohorts=2, retirement_failures=2)
    store.evaluate_multi_cohort([
        CohortEvidence("cap", "a", True, 1.0, "domain-a", "family-a", "a"),
        CohortEvidence("cap", "b", True, 1.0, "domain-b", "family-b", "b"),
    ])
    store.evaluate_canary("cap", [CanaryEvidence("cap", True), CanaryEvidence("cap", True), CanaryEvidence("cap", True)])
    assert store.evaluate_canary("cap", [CanaryEvidence("cap", False), CanaryEvidence("cap", False)]).state.status == "rolled_back"
    assert store.evaluate_canary("cap", [CanaryEvidence("cap", False)]).state.status == "retired"
