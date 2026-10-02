from anybridge.providers import select_provider, provider_profiles

def test_provider_selection_prefers_explicit_provider():
    assert select_provider(["bdd"], preferred="selenium", browser="chrome") == "selenium"

def test_provider_selection_uses_capabilities_and_browser():
    assert select_provider(["webmcp"], browser="edge") == "selenium"
    assert select_provider(["webmcp"], browser="webkit") == "playwright"

def test_provider_profiles_are_explicit():
    assert {p.name for p in provider_profiles()} == {"playwright", "selenium"}
