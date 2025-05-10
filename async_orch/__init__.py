import asyncio
from datetime import timedelta  # Import timedelta
from enum import Enum, auto
from typing import Callable, Union, Iterable, Any, Awaitable
import inspect
import sys


# --- Event Bus for state notifications ------------------------------------
class EventBus:
    def __init__(self):
        self._subscribers: list[Callable[[dict], Awaitable[None]]] = []

    def subscribe(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Subscribe to task/circuit events."""
        self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Unsubscribe from task/circuit events."""
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    async def emit(self, event: dict) -> None:
        """Emit an event to all subscribers."""
        for handler in self._subscribers:
            # Fire and forget; subscriber handles its own errors
            asyncio.create_task(handler(event))


# Global event bus
event_bus = EventBus()


# --- Task States -----------------------------------------------------------
class TaskState(Enum):
    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    RETRYING = auto()
    CANCELLED = auto()


# A TaskFn is either a coroutine function or a sync function.
TaskFn = Callable[..., Union[Awaitable[Any], Any]]


# --- Core Task -------------------------------------------------------------
class _TaskRunner:
    def __init__(self, fn: TaskFn, *args, name: str = None, **kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.name = name or fn.__name__
        self.state = TaskState.PENDING

    async def _set_state(self, state: TaskState, **meta) -> None:
        self.state = state
        await event_bus.emit({"type": "task", "task": self, "state": state, **meta})

    async def _execute_with_policies(self) -> Any:
        # Default: just execute once. Override or monkey-patch for retry/circuit.
        result = self.fn(*self.args, **self.kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def run(self, *input_args, **input_kwargs) -> Any:
        await self._set_state(TaskState.RUNNING)
        try:
            # If input_args or input_kwargs are provided, override self.args/kwargs for this run
            if input_args or input_kwargs:
                result = self.fn(*input_args, **input_kwargs)
            else:
                result = await self._execute_with_policies()
            if asyncio.iscoroutine(result):
                result = await result
            await self._set_state(TaskState.SUCCEEDED, result=result)
            return result
        except Exception as exc:
            await self._set_state(TaskState.FAILED, error=exc)
            raise


# --- Sequence Definition ---------------------------------------------------
class Sequence:
    def __init__(
        self, *steps: Union[TaskFn, "Sequence", "Parallel"], name: str = None
    ):  # Changed ParallelTaskRunner to Parallel
        processed_steps = []
        for step_item in steps:
            if callable(step_item) and not isinstance(
                step_item, (Sequence, Parallel)
            ):  # Changed
                processed_steps.append(step_item)
            elif isinstance(step_item, (Sequence, Parallel)):  # Changed
                processed_steps.append(step_item)
            else:
                raise TypeError(
                    f"Invalid step type: {type(step_item)}. Expected TaskFn, Sequence, or Parallel."
                )
        self.steps = tuple(processed_steps)
        self.name = name or self.__class__.__name__


# --- Internal Sequence Runner ----------------------------------------------
class _SequentialTaskRunner:
    def __init__(self, sequence_def: Sequence, name: str = None):
        self.definition = sequence_def
        self.name = name or self.definition.name

        self._executable_steps = []
        for step_def_item in self.definition.steps:
            if callable(step_def_item) and not isinstance(
                step_def_item, (Sequence, Parallel)
            ):  # Changed
                self._executable_steps.append(_TaskRunner(fn=step_def_item))
            elif isinstance(step_def_item, Sequence):
                self._executable_steps.append(
                    _SequentialTaskRunner(sequence_def=step_def_item)
                )
            elif isinstance(step_def_item, Parallel):  # Changed
                self._executable_steps.append(
                    _ParallelTaskRunner(parallel_def=step_def_item)
                )  # Now uses _ParallelTaskRunner
            else:
                # which is not expected if Sequence is built with TaskFn, Sequence, Parallel defs.
                # However, to be robust for now if it's already a _TaskRunner (e.g. from direct run call)
                if isinstance(step_def_item, _TaskRunner):
                    self._executable_steps.append(step_def_item)
                else:
                    raise TypeError(
                        f"Invalid step type for execution: {type(step_def_item)}"
                    )

    async def run(self) -> Any:
        result = None
        if not self._executable_steps:
            return []
        for i, step_executor in enumerate(self._executable_steps):
            if i == 0:
                result = await step_executor.run()
            else:
                # step_executor is _TaskRunner, _SequentialTaskRunner, or ParallelTaskRunner (soon _ParallelTaskRunner)
                if isinstance(step_executor, _TaskRunner):
                    sig = inspect.signature(step_executor.fn)
                    params = list(sig.parameters.values())
                    if params and (params[0].name in ("self", "cls")):
                        params = params[1:]
                    if len(params) > 0:
                        result = await step_executor.run(result)
                    else:
                        result = await step_executor.run()
                else:
                    result = await step_executor.run()
        return result


# --- Parallel Definition ---------------------------------------------------
class Parallel:
    def __init__(
        self,
        *tasks: Union[TaskFn, Sequence, "Parallel"],
        max_workers: int = None,
        name: str = None,
    ):
        processed_tasks = []
        for task_item in tasks:
            if callable(task_item) and not isinstance(task_item, (Sequence, Parallel)):
                processed_tasks.append(task_item)
            elif isinstance(task_item, (Sequence, Parallel)):
                processed_tasks.append(task_item)
            else:
                raise TypeError(
                    f"Invalid task type: {type(task_item)}. Expected TaskFn, Sequence, or Parallel."
                )
        self.tasks = tuple(processed_tasks)
        self.max_workers = max_workers
        self.name = name or self.__class__.__name__


# --- Internal Parallel Runner ----------------------------------------------
class _ParallelTaskRunner:
    def __init__(self, parallel_def: Parallel, name: str = None):
        self.definition = parallel_def
        self.name = name or self.definition.name

        self._executable_tasks = []
        for task_def_item in self.definition.tasks:
            if callable(task_def_item) and not isinstance(
                task_def_item, (Sequence, Parallel)
            ):  # TaskFn
                self._executable_tasks.append(_TaskRunner(fn=task_def_item))
            elif isinstance(task_def_item, Sequence):
                self._executable_tasks.append(
                    _SequentialTaskRunner(sequence_def=task_def_item)
                )
            elif isinstance(task_def_item, Parallel):
                self._executable_tasks.append(
                    _ParallelTaskRunner(parallel_def=task_def_item)
                )  # Recursive
            elif isinstance(task_def_item, _TaskRunner):  # Already an executable
                self._executable_tasks.append(task_def_item)
            else:
                raise TypeError(
                    f"Invalid task type for execution: {type(task_def_item)}"
                )

    async def run(self) -> list[Any]:
        if self.definition.max_workers:
            semaphore = asyncio.Semaphore(self.definition.max_workers)

            async def sem_task_executor(task_executor):  # Renamed task to task_executor
                async with semaphore:
                    return await task_executor.run()

            coroutines = [sem_task_executor(ex) for ex in self._executable_tasks]
        else:
            coroutines = [ex.run() for ex in self._executable_tasks]

        results = []
        try:
            async with asyncio.TaskGroup() as task_group:
                tasks = [task_group.create_task(c) for c in coroutines]
            for t in tasks:
                results.append(t.result())
            return results
        except Exception as exc:
            # Python 3.11+: Unwrap ExceptionGroup if only one exception
            if (
                sys.version_info >= (3, 11)
                and exc.__class__.__name__ == "ExceptionGroup"
            ):
                exception_group = exc
                if (
                    hasattr(exception_group, "exceptions")
                    and len(exception_group.exceptions) == 1
                ):
                    raise exception_group.exceptions[0]
            raise


# --- Circuit Breaker Definition --------------------------------------------
from aiobreaker import (
    CircuitBreaker,
    CircuitBreakerError,
)  # Keep import here for CircuitBreakerError


class CircuitDefinition:
    def __init__(
        self,
        *tasks: Union[TaskFn, Sequence, Parallel],
        fail_max: int = 5,
        reset_timeout: int = 60,
        name: str = None,
    ):
        # Tasks for a circuit are typically run in parallel under the breaker.
        # We'll store them as a Parallel definition internally.
        self.task_definition = Parallel(*tasks)  # Store tasks as a Parallel definition
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.name = name or self.__class__.__name__
        self._runner_instance: _CircuitGroupTaskRunner = None  # Store runner instance


# --- Internal Circuit Group Runner -----------------------------------------
class _CircuitGroupTaskRunner:
    class _EventListener:
        def __init__(self, circuit_runner):  # Changed circuit_group to circuit_runner
            self.circuit_runner = circuit_runner  # Changed

        def state_change(self, breaker, old_state, new_state):  # Made synchronous
            # Assuming breaker.current_state is the string name of the new state (e.g., "OPEN")
            # And old_state/new_state are objects without .name and unhelpful __str__

            current_state_str = (
                breaker.current_state
            )  # This should be the string name of new_state

            # For old_state, it's harder to get a clean string name if the object itself doesn't provide it.
            # We'll use str() as a fallback for logging.
            old_name_repr = str(old_state)

            event_payload = {
                "type": "circuit",
                "circuit_runner_name": self.circuit_runner.name,
                "circuit_definition_name": self.circuit_runner.definition.name,
                "old_state": old_name_repr,  # Log representation of old_state object
                "new_state": current_state_str,  # Use string name from breaker for new_state
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_bus.emit(event_payload))
            except RuntimeError:  # Fallback if no running loop
                asyncio.run(event_bus.emit(event_payload))  # Less ideal, but for safety

        def before_call(self, breaker, func, *args, **kwargs):
            pass

        def failure(self, breaker, exc):
            pass

        def success(self, breaker):
            pass

        def call(self, breaker, func, *args, **kwargs):
            pass

        def open(self, breaker):
            pass

        def half_open(self, breaker):
            pass

        def close(self, breaker):
            pass

    def __init__(self, circuit_def: CircuitDefinition, name: str = None):
        self.definition = circuit_def
        self.name = name or self.definition.name or self.__class__.__name__

        self.breaker = CircuitBreaker(
            fail_max=self.definition.fail_max,
            timeout_duration=(
                timedelta(seconds=self.definition.reset_timeout)
                if not isinstance(self.definition.reset_timeout, timedelta)
                else self.definition.reset_timeout
            ),
        )

        self._listener = _CircuitGroupTaskRunner._EventListener(self)
        self.breaker.add_listener(self._listener)

        # The tasks to run under the circuit breaker are defined as a Parallel group
        # in the CircuitDefinition. We need an executor for this Parallel definition.
        self._parallel_executor = _ParallelTaskRunner(
            parallel_def=self.definition.task_definition
        )

    @property
    def current_state(self):
        return self.breaker.current_state.name

    @property
    def failure_count(self):
        return self.breaker.fail_counter

    async def run(self) -> list[Any]:
        try:
            # Execute the underlying Parallel group via its runner
            return await self.breaker.call_async(self._parallel_executor.run)
        except CircuitBreakerError as circuit_breaker_error:
            await event_bus.emit(
                {
                    "type": "circuit",
                    "circuit_runner_name": self.name,
                    "circuit_definition_name": self.definition.name,
                    "state": self.breaker.current_state,  # Assuming this is the string state name
                    "error": circuit_breaker_error,
                }
            )
            raise


# --- Convenience Entrypoint -----------------------------------------------
async def run(
    task: Union[_TaskRunner, Sequence, Parallel, CircuitDefinition],
) -> Any:  # Added CircuitDefinition
    """Top-level runner for any _TaskRunner/Sequence/Parallel/CircuitDefinition."""
    if isinstance(task, Sequence):
        return await _SequentialTaskRunner(sequence_def=task).run()
    elif isinstance(task, Parallel):
        return await _ParallelTaskRunner(parallel_def=task).run()
    elif isinstance(task, CircuitDefinition):
        if task._runner_instance is None:
            task._runner_instance = _CircuitGroupTaskRunner(circuit_def=task)
        return await task._runner_instance.run()
    elif isinstance(task, _TaskRunner):  # Direct execution of a single _TaskRunner
        return await task.run()
    else:
        raise TypeError(f"Unsupported task type for run(): {type(task)}")
