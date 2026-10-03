from anybridge.holdout_generation import HoldoutGenerator, BenchmarkObservation
from anybridge.capability_composition import CapabilityPrimitive
from anybridge.holdout_benchmark import HoldoutBenchmark


def test_benchmark_requires_independent_outcomes():
    g=HoldoutGenerator()
    c=g.generate([CapabilityPrimitive("cap","content","boundary",confidence=.9)],target_domains=("extension",))
    case=c[0]
    b=HoldoutBenchmark(min_attempts=2)
    b.ingest(c,[
        BenchmarkObservation(case.case_id,True,1.0,True),
        BenchmarkObservation(case.case_id,True,1.0,True),
    ])
    assert b.results()[0].status=="validated_holdout"


def test_non_independent_outcomes_do_not_become_evidence():
    g=HoldoutGenerator()
    c=g.generate([CapabilityPrimitive("cap","content","boundary",confidence=.9)],target_domains=("extension",))
    case=c[0]
    b=HoldoutBenchmark(min_attempts=1)
    b.ingest(c,[BenchmarkObservation(case.case_id,True,1.0,False)])
    assert not b.results()


def test_failed_and_insufficient_benchmarks_are_distinct():
    g=HoldoutGenerator()
    c=g.generate([CapabilityPrimitive("cap","content","boundary",confidence=.9)],target_domains=("extension",))
    case=c[0]
    b=HoldoutBenchmark(min_attempts=2)
    b.ingest(c,[BenchmarkObservation(case.case_id,False,1.0,True)])
    assert b.results()[0].status=="insufficient_evidence"
    b.ingest(c,[BenchmarkObservation(case.case_id,False,1.0,True)])
    assert b.results()[0].status=="failed_holdout"
