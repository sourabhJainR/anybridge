from anybridge.evidence_aware_promotion import CohortEvidence, EvidenceAwarePromotionStore

def obs(cap, cohort, passed=True, confidence=1.0):
    return CohortEvidence(cap, cohort, passed, confidence, cohort, cohort)

def test_one_cohort_cannot_promote():
    s=EvidenceAwarePromotionStore(min_cohorts=2)
    d=s.ingest([obs("cap","a"),obs("cap","a")])[0]
    assert d.status=="candidate"

def test_independent_cohorts_enter_canary():
    s=EvidenceAwarePromotionStore(min_cohorts=2)
    d=s.ingest([obs("cap","a"),obs("cap","b")])[0]
    assert d.status=="canary"

def test_weak_cohort_blocks_promotion():
    s=EvidenceAwarePromotionStore(min_cohorts=2)
    d=s.ingest([obs("cap","a"),obs("cap","b",False)])[0]
    assert d.status=="candidate"

def test_canary_graduates_on_strong_latest_evidence():
    s=EvidenceAwarePromotionStore(min_cohorts=2)
    s.ingest([obs("cap","a"),obs("cap","b")])
    d=s.ingest([obs("cap","a"),obs("cap","b")])[0]
    assert d.status=="graduated"

def test_decay_quarantines_then_retires():
    s=EvidenceAwarePromotionStore(min_cohorts=2, retirement_failures=2)
    s.ingest([obs("cap","a"),obs("cap","b")])
    s.ingest([obs("cap","a"),obs("cap","b")])
    assert s.ingest([obs("cap","a",False,0.5),obs("cap","b",False,0.5)])[0].status=="quarantined"
    assert s.ingest([obs("cap","a",False,0.5),obs("cap","b",False,0.5)])[0].status=="retired"

def test_bounds_and_determinism():
    s=EvidenceAwarePromotionStore(max_observations=2)
    s.ingest([obs("b","z"),obs("a","x"),obs("c","y")])
    assert len(s.export()["observations"])==2
