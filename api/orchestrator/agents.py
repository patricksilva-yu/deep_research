from typing import Dict, List
from dataclasses import dataclass, field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from dotenv import load_dotenv

from api.web_search.agents import web_search_agent
from api.verification.agents import verification_agent
from api.code_executor.agents import code_execution_agent
from api.summarizer.agents import summarizer_agent
from api.summarizer.models import FinalReportInput, CompletedTaskSummary, VerificationSummary
from api.verification.models import SourceAssessment, ConsistencyIssue
from .models import OrchestratorOutput, ResearchTask
from .prompts import ORCHESTRATOR_INSTRUCTIONS

load_dotenv()


@dataclass
class OrchestratorState:
    """Per-request state for orchestrator agent runs.

    This class holds mutable state for a single orchestration run,
    ensuring proper isolation between concurrent requests.

    Attributes:
        completed_tasks: Dictionary mapping task_id to task results.
                        Each request gets its own isolated dictionary.
    """
    completed_tasks: Dict[str, dict] = field(default_factory=dict)

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='low',
    openai_reasoning_summary='detailed'
)

orchestrator_agent = Agent(
    'openai-responses:gpt-5',
    deps_type=OrchestratorState,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    output_type=OrchestratorOutput,
    retries=3,
    model_settings=model_settings
)


@orchestrator_agent.tool
async def execute_search_task(ctx: RunContext[OrchestratorState], task: ResearchTask) -> dict:
    """Execute a research task using the web search agent.

    This tool allows the orchestrator to delegate search tasks to the web search agent.
    Pass a ResearchTask with task_id, description, and search_query.
    """
    result = await web_search_agent.run(task.search_query)

    # Use model_dump() and add task metadata
    task_result = {
        "task_id": task.task_id,
        "description": task.description,
        **result.output.model_dump()  # Spreads findings, summary, gaps, etc.
    }
    ctx.deps.completed_tasks[task.task_id] = task_result
    return task_result


@orchestrator_agent.tool_plain
async def verify_findings(content: str, sources: List[str]) -> dict:
    """Verify research findings for quality, credibility, and consistency.

    Use this tool after completing search tasks to validate the research quality.

    Args:
        content: The research findings and summaries to verify
        sources: List of source URLs cited in the research

    Returns:
        Verification results including quality rating and issues found
    """
    # Construct verification prompt
    verification_prompt = f"Please verify the following research content:\n\n{content}"
    verification_prompt += f"\n\nSources cited:\n" + "\n".join(f"- {source}" for source in sources)

    result = await verification_agent.run(verification_prompt)

    # Use Pydantic's model_dump() to automatically convert model to dict
    verification_result = result.output.model_dump()

    return verification_result


@orchestrator_agent.tool_plain
async def execute_code_task(task: str) -> dict:
    """Execute Python code for data analysis, calculations, or processing.

    Use this tool when you need to perform computational tasks, data analysis,
    or any programmatic processing as part of the research workflow.

    Args:
        task: Description of what code needs to be executed

    Returns:
        Code execution results including summary and outputs
    """
    result = await code_execution_agent.run(task)

    # Use Pydantic's model_dump() to automatically convert model to dict
    code_result = result.output.model_dump()

    return code_result


@orchestrator_agent.tool
async def generate_final_report(ctx: RunContext[OrchestratorState], mission: str, verification_results: dict = None) -> dict:
    """Generate a comprehensive final research report from all completed tasks.

    Use this tool as the FINAL step after executing all search tasks and verification.
    This produces a polished, synthesized report with executive summary, detailed sections,
    and source citations.

    Args:
        mission: The original research mission/question
        verification_results: Optional verification results dict from verify_findings tool

    Returns:
        Final report with executive summary, sections, sources, and quality notes
    """
    # Build completed task summaries from stored tasks
    completed_tasks = []
    for task_id, task_data in ctx.deps.completed_tasks.items():
        completed_tasks.append(
            CompletedTaskSummary(
                task_id=task_data["task_id"],
                description=task_data["description"],
                summary=task_data["summary"],
                findings=task_data["findings"],
                gaps=task_data.get("gaps")
            )
        )

    # Build verification summary if provided
    verification_summary = None
    if verification_results:
        # Convert dict results to proper model instances
        source_assessments = [
            SourceAssessment(**sa) for sa in verification_results["source_assessments"]
        ]
        consistency_issues = [
            ConsistencyIssue(**ci) for ci in verification_results["consistency_issues"]
        ]

        verification_summary = VerificationSummary(
            overall_quality_rating=verification_results["overall_quality_rating"],
            approved_for_use=verification_results["approved_for_use"],
            source_assessments=source_assessments,
            consistency_issues=consistency_issues,
            critical_flags=verification_results.get("critical_flags"),
            improvement_priority=verification_results["improvement_priority"]
        )

    # Create input for summarizer
    report_input = FinalReportInput(
        mission=mission,
        tasks=completed_tasks,
        verification=verification_summary
    )

    # Generate final report - convert to JSON string for the agent
    result = await summarizer_agent.run(report_input.model_dump_json(indent=2))

    # Use Pydantic's model_dump() to automatically convert model to dict
    final_report = result.output.model_dump()

    return final_report
