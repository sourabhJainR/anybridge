from pathlib import Path
from anybridge.bdd import parse_feature

def test_parse_feature_and_scenario_outline():
    feature = parse_feature("""Feature: Login
  Background:
    Given I wait for text "Ready"
  Scenario Outline: login
    Given open the page https://example.test
    Then I should see "<text>"
    Examples:
      | text |
      | Ready |
      | Done |
""")
    assert feature.name == "Login"
    assert len(feature.background) == 1
    assert len(feature.scenarios) == 1
    assert feature.scenarios[0].name == "login"
    assert any(step.keyword == "Examples" for step in feature.scenarios[0].steps)
