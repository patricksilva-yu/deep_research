import contextlib
import io
import time

from .models import CodeExecutionResult, CodeExecutorOutput


async def execute_python_task(task: str) -> CodeExecutorOutput:
    stdout_buffer = io.StringIO()
    local_env = {}
    started_at = time.perf_counter()

    try:
        with contextlib.redirect_stdout(stdout_buffer):
            exec(task, {"__builtins__": __builtins__}, local_env)
        execution_time = time.perf_counter() - started_at
        output = stdout_buffer.getvalue() or None
        summary = "Executed Python task successfully."
        if output:
            summary = "Executed Python task and captured output."
        return CodeExecutorOutput(
            summary=summary,
            executions=[
                CodeExecutionResult(
                    code=task,
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
                    code=task,
                    output=stdout_buffer.getvalue() or None,
                    error=str(exc),
                    execution_time=execution_time,
                )
            ],
            next_steps=["Review the error and adjust the analysis code before retrying."],
        )
