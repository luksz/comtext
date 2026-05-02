"""Multi-agent orchestrator: Researcher → Planner → Coder → Reviewer."""
from __future__ import annotations

from dataclasses import dataclass, field

import anthropic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from pce.agents.roles import CODER_SYSTEM, PLANNER_SYSTEM, RESEARCHER_SYSTEM, REVIEWER_SYSTEM
from pce.agents.tools import COMTEXT_TOOLS, _tool_write_note, execute_tool
from pce.config import settings

log = structlog.get_logger()


@dataclass
class AgentOutput:
    role: str
    text: str
    tool_calls: int = 0


@dataclass
class TeamResult:
    task: str
    research: str
    plan: str
    implementation: str
    review: str
    agents: list[AgentOutput] = field(default_factory=list)


def _extract_text(content: list) -> str:
    """Pull text from a list of content blocks (ignores ThinkingBlock)."""
    return "\n".join(b.text for b in content if hasattr(b, "text") and b.text)


async def _run_agent(
    client: anthropic.AsyncAnthropic,
    role: str,
    system: str,
    initial_messages: list[dict],
    session: AsyncSession,
    max_tool_calls: int = 10,
) -> AgentOutput:
    messages = list(initial_messages)
    tool_calls = 0
    last_text = ""

    for _ in range(max_tool_calls + 1):
        response = await client.messages.create(
            model=settings.agent_model,
            max_tokens=8096,
            thinking={"type": "adaptive"},
            system=system,
            tools=COMTEXT_TOOLS,
            messages=messages,
        )
        log.info(
            "agent_turn",
            role=role,
            stop_reason=response.stop_reason,
            in_tok=response.usage.input_tokens,
            out_tok=response.usage.output_tokens,
        )

        candidate_text = _extract_text(response.content)
        if candidate_text:
            last_text = candidate_text

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            # Pass all blocks back (including thinking blocks) as required by the API
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls += 1
                    log.info("tool_call", role=role, tool=block.name, input=block.input)
                    result = await execute_tool(block.name, block.input, session)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return AgentOutput(role=role, text=last_text, tool_calls=tool_calls)


async def run_team(task: str, session: AsyncSession) -> TeamResult:
    """Run the full Researcher → Planner → Coder → Reviewer pipeline."""
    if not settings.anthropic_api_key:
        raise ValueError(
            "PCE_ANTHROPIC_API_KEY must be set to use the team feature. "
            "Add it to your .env file: PCE_ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # --- Researcher ---
    log.info("team_stage", stage="researcher")
    researcher = await _run_agent(
        client, "researcher", RESEARCHER_SYSTEM,
        [{"role": "user", "content": (
            f"Task: {task}\n\n"
            "Search Comtext for all relevant context and produce your research summary."
        )}],
        session,
    )

    # --- Planner ---
    log.info("team_stage", stage="planner")
    planner = await _run_agent(
        client, "planner", PLANNER_SYSTEM,
        [{"role": "user", "content": (
            f"Task: {task}\n\n"
            f"## Research Findings\n{researcher.text}\n\n"
            "Produce a detailed execution plan."
        )}],
        session,
    )

    # --- Coder ---
    log.info("team_stage", stage="coder")
    coder = await _run_agent(
        client, "coder", CODER_SYSTEM,
        [{"role": "user", "content": (
            f"Task: {task}\n\n"
            f"## Research\n{researcher.text}\n\n"
            f"## Plan\n{planner.text}\n\n"
            "Implement the plan. Save your implementation to Comtext using write_note."
        )}],
        session,
    )

    # --- Reviewer ---
    log.info("team_stage", stage="reviewer")
    reviewer = await _run_agent(
        client, "reviewer", REVIEWER_SYSTEM,
        [{"role": "user", "content": (
            f"Task: {task}\n\n"
            f"## Research\n{researcher.text}\n\n"
            f"## Plan\n{planner.text}\n\n"
            f"## Implementation\n{coder.text}\n\n"
            "Review the implementation and provide your verdict."
        )}],
        session,
    )

    # Store the full team report back to Comtext
    full_report = (
        f"# Team Report: {task}\n\n"
        f"## Research\n{researcher.text}\n\n"
        f"## Plan\n{planner.text}\n\n"
        f"## Implementation\n{coder.text}\n\n"
        f"## Review\n{reviewer.text}"
    )
    await _tool_write_note(
        title=f"Team: {task[:80]}",
        content=full_report,
        tags=["agent", "team-report"],
        session=session,
    )
    log.info("team_done", task=task)

    return TeamResult(
        task=task,
        research=researcher.text,
        plan=planner.text,
        implementation=coder.text,
        review=reviewer.text,
        agents=[researcher, planner, coder, reviewer],
    )
