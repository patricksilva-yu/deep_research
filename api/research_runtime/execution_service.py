import ast
import contextlib
import io
import os
import time

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import CodeExecutionResult, CodeExecutorOutput

load_dotenv()

EXECUTION_MODEL = os.getenv("RESEARCH_EXECUTION_MODEL", "openai-responses:gpt-5.4")


class PythonAnalysisPlan(BaseModel):
    python_code: str = Field(description="Pure Python code to execute for the analysis task")
    notes: str = Field(description="Short note on what the code does and any important constraints")


analysis_codegen_agent = Agent(
    EXECUTION_MODEL,
    instructions=(
        "Convert an analysis request into executable Python code that directly answers the request. "
        "Return only pure Python that can run with the standard library. "
        "Do not rely on third-party packages unless the request explicitly requires them and they are guaranteed to exist. "
        "Prefer printing structured results when the caller asked for tables, summaries, or calculated outputs. "
        "Do not write reusable frameworks, classes, tests, CLI wrappers, or examples. "
        "Do not include markdown fences, docstrings, or comments unless they are essential. "
        "Keep the code short and literal: directly compute the requested answer with the given numbers and assumptions. "
        "Examples: for 'Calculate 2+2 and print it', return `print(2 + 2)`. "
        "For a budgeting request, create variables from the stated assumptions, compute totals, and print the result."
    ),
    output_type=PythonAnalysisPlan,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="low",
        openai_reasoning_summary="auto",
    ),
    retries=2,
)


def _looks_like_python(task: str) -> bool:
    try:
        ast.parse(task)
    except SyntaxError:
        return False
    return True


def _strip_code_fences(code: str) -> str:
    stripped = code.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _code_is_overengineered(code: str) -> bool:
    lines = [line for line in code.splitlines() if line.strip()]
    disallowed_markers = (
        "if __name__ ==",
        "class ",
        '"""',
        "argparse",
        "unittest",
    )
    return len(lines) > 60 or any(marker in code for marker in disallowed_markers)


async def _generate_python_code(task: str, execution_error: str | None = None) -> PythonAnalysisPlan:
    prompt = (
        "Convert the following analysis request into short executable Python.\n"
        "Requirements:\n"
        "- return code that directly solves the task\n"
        "- use only the standard library unless a dependency is explicitly required\n"
        "- print the requested outputs\n"
        "- keep the program as short as possible\n"
        "- do not build frameworks, classes, tests, examples, or CLI wrappers\n"
        f"\nTask:\n{task}\n"
    )
    if execution_error:
        prompt += f"\nPrior execution error to fix:\n{execution_error}\n"
    plan: PythonAnalysisPlan | None = None
    for _ in range(2):
        result = await analysis_codegen_agent.run(prompt)
        plan = result.output
        plan.python_code = _strip_code_fences(plan.python_code)
        if not _code_is_overengineered(plan.python_code):
            return plan
        prompt += "\nThe previous code was overengineered. Return a much shorter direct solution.\n"
    return plan


def _run_python(code: str) -> CodeExecutorOutput:
    stdout_buffer = io.StringIO()
    local_env = {}
    started_at = time.perf_counter()

    try:
        with contextlib.redirect_stdout(stdout_buffer):
            exec(code, {"__builtins__": __builtins__}, local_env)
        execution_time = time.perf_counter() - started_at
        output = stdout_buffer.getvalue() or None
        summary = "Executed Python task successfully."
        if output:
            summary = "Executed Python task and captured output."
        return CodeExecutorOutput(
            summary=summary,
            executions=[
                CodeExecutionResult(
                    code=code,
                    output=output,
                    error=None,
                    execution_time=execution_time,
                )
            ],
            next_steps=None,
        )
    except Exception as exc:
        execution_time = time.perf_counter() - started_at
        return CodeExecutorOutput(
            summary="Python task execution failed.",
            executions=[
                CodeExecutionResult(
                    code=code,
                    output=stdout_buffer.getvalue() or None,
                    error=str(exc),
                    execution_time=execution_time,
                )
            ],
            next_steps=["Review the error and adjust the analysis code before retrying."],
        )


async def execute_python_task(task: str) -> CodeExecutorOutput:
    code = task
    translation_note: str | None = None
    if not _looks_like_python(task):
        plan = await _generate_python_code(task)
        code = plan.python_code
        translation_note = plan.notes

    first_attempt = _run_python(code)
    if first_attempt.executions[0].error and (
        "No module named" in first_attempt.executions[0].error
        or "invalid syntax" in first_attempt.executions[0].error
    ):
        plan = await _generate_python_code(task, execution_error=first_attempt.executions[0].error)
        retry = _run_python(plan.python_code)
        translation_note = plan.notes
        if retry.executions and translation_note:
            retry.summary = f"{retry.summary} Generated Python from the analysis request."
            retry.next_steps = None
        return retry

    if first_attempt.executions and translation_note:
        first_attempt.summary = f"{first_attempt.summary} Generated Python from the analysis request."
        first_attempt.next_steps = None
    return first_attempt
