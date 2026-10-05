from fastapi.testclient import TestClient
from tc_orchestrator.api import create_app
from tc_orchestrator.config import Settings
from tc_orchestrator.task_store import TaskStore
from tests.conftest import FakeWorkspaceClient

def settings():
    return Settings(brain_base_url="https://example.com/v1",brain_api_key=None,brain_model="m",daemon_addr="127.0.0.1:1",max_agent_steps=5,host="127.0.0.1",port=8080,database_url=None,require_approval=True,approval_expiry_seconds=300)

def client(): return TestClient(create_app(settings=settings(),store=TaskStore(),client=FakeWorkspaceClient()))

def test_plan_create_approve_and_task_gate():
    c=client(); r=c.post("/v1/plans",json={"prompt":"Create a Python project and run pytest."}); assert r.status_code==200
    plan=r.json()["plan"]; token=r.json()["owner_token"]; assert plan["status"]=="DRAFT"
    assert c.post("/v1/tasks",json={"prompt":"build","plan_id":plan["plan_id"]}).status_code==409
    assert c.post(f"/v1/plans/{plan['plan_id']}/approve",json={"approved":True},headers={"x-tc-plan-owner-token":"wrong"}).status_code==403
    approved=c.post(f"/v1/plans/{plan['plan_id']}/approve",json={"approved":True},headers={"x-tc-plan-owner-token":token}); assert approved.status_code==200 and approved.json()["status"]=="READY"
    task=c.post("/v1/tasks",json={"prompt":"build","plan_id":plan["plan_id"]}); assert task.status_code==200 and task.json()["plan_id"]==plan["plan_id"]

def test_plan_project_mismatch_rejected():
    c=client(); a=c.post("/v1/projects",json={"name":"a","description":"","workspace_path":"a"}).json(); b=c.post("/v1/projects",json={"name":"b","description":"","workspace_path":"b"}).json(); r=c.post("/v1/plans",json={"prompt":"do work","project_id":a["id"]}).json(); c.post(f"/v1/plans/{r['plan']['plan_id']}/approve",json={"approved":True},headers={"x-tc-plan-owner-token":r["owner_token"]}); assert c.post("/v1/tasks",json={"prompt":"do work","project_id":b["id"],"plan_id":r["plan"]["plan_id"]}).status_code==409

def test_plan_context_endpoint():
    c=client(); r=c.post("/v1/plans",json={"prompt":"Implement auth and run tests."}).json(); body=c.get(f"/v1/plans/{r['plan']['plan_id']}/context").json(); assert "Implement auth and run tests." in body["context_text"]; assert "acceptance_criteria:" in body["context_text"]
