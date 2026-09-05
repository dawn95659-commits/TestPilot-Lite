from testpilot.models import AgentState, Phase
from testpilot.planner import HeuristicPlanner


planner = HeuristicPlanner()

state = AgentState(
    goal="demo",
    openapi_url="http://127.0.0.1:8001/openapi.json",
)

for phase in [
    Phase.INSPECTING,
    Phase.GENERATING,
    Phase.EXECUTING,
    Phase.SEARCHING_BUGS,
    Phase.REPORTING,
    Phase.COMPLETED,
]:
    state.phase = phase
    decision = planner.decide(state)

    print(
        phase.value,
        "->",
        decision.tool_name,
        "->",
        decision.reason,
    )
