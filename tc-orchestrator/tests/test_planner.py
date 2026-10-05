from tc_orchestrator.planner import build_plan

def test_build_plan_is_deterministic_and_verification_first():
    a=build_plan("Fix the failing pytest suite and verify it passes.")
    b=build_plan("Fix the failing pytest suite and verify it passes.")
    assert a==b
    ids=[x["id"] for x in a["steps"]]
    assert ids[0]=="inspect" and "repair" in ids and ids[-1]=="verify"
    assert a["acceptance_criteria"] and a["risks"]
