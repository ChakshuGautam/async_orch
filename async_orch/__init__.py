import asyncio
from enum import Enum, auto
from typing import Callable, Union, Iterable, Any, Awaitable
import inspect
import sys


# --- Event Bus for state notifications ------------------------------------
class EventBus:
    def __init__(self):
        self._subs: list[Callable[[dict], Awaitable[None]]] = []

    def subscribe(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        """Subscribe to task/circuit events."""
        self._subs.append(fn)

    def unsubscribe(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        """Unsubscribe from task/circuit events."""
        if fn in self._subs:
            self._subs.remove(fn)

    async def emit(self, event: dict) -> None:
        """Emit an event to all subscribers."""
        for fn in self._subs:
            # Fire and forget; subscriber handles its own errors
            asyncio.create_task(fn(event))


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
class TaskRunner:
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


# --- Sequence --------------------------------------------------------------
class Sequence:
    def __init__(
        self, *steps: Union[TaskRunner, "Sequence", "Parallel"], name: str = None
    ):
        self.steps = steps
        self.name = name or "Sequence"

    async def run(self) -> Any:
        result = None
        if not self.steps:
            return []
        for i, step in enumerate(self.steps):
            if i == 0:
                result = await step.run()
            else:
                if isinstance(step, TaskRunner):
                    sig = inspect.signature(step.fn)
                    params = list(sig.parameters.values())
                    if params and (params[0].name in ("self", "cls")):
                        params = params[1:]
                    if len(params) > 0:
                        result = await step.run(result)
                    else:
                        result = await step.run()
                else:
                    result = await step.run()
        return result


# --- Parallel --------------------------------------------------------------
class Parallel:
    def __init__(
        self,
        *tasks: Union[TaskRunner, Sequence, "Parallel"],
        max_workers: int = None,
        name: str = None,
    ):
        self.tasks = tasks
        self.max_workers = max_workers
        self.name = name or "Parallel"

    async def run(self) -> list[Any]:
        if self.max_workers:
            sem = asyncio.Semaphore(self.max_workers)

            async def sem_task(task):
                async with sem:
                    return await task.run()

            coros = [sem_task(task) for task in self.tasks]
        else:
            coros = [task.run() for task in self.tasks]

        results = []
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(c) for c in coros]
            for t in tasks:
                results.append(t.result())
            return results
        except Exception as exc:
            # Python 3.11+: Unwrap ExceptionGroup if only one exception
            if (
                sys.version_info >= (3, 11)
                and exc.__class__.__name__ == "ExceptionGroup"
            ):
                eg = exc
                if hasattr(eg, "exceptions") and len(eg.exceptions) == 1:
                    raise eg.exceptions[0]
            raise


# --- Circuit Breaker -------------------------------------------------------
from aiobreaker import CircuitBreaker, CircuitBreakerError


class CircuitGroup:
    class _EventListener:
        def __init__(self, circuit_group):
            self.circuit_group = circuit_group

        async def state_change(self, breaker, old_state, new_state):
            await event_bus.emit(
                {
                    "type": "circuit",
                    "circuit": self.circuit_group,
                    "old_state": old_state,
                    "new_state": new_state,
                }
            )

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

    def __init__(
        self,
        *tasks: Union[TaskRunner, Sequence, Parallel],
        fail_max: int = 5,
        reset_timeout: int = 60,
        name: str = None,
    ):
        self.tasks = tasks
        self.breaker = CircuitBreaker(fail_max=fail_max)
        self.breaker.reset_timeout = reset_timeout  # Set as a property
        self.name = name or "CircuitGroup"

        # Subscribe to breaker state changes using aiobreaker's listener system
        self._listener = CircuitGroup._EventListener(self)
        self.breaker.add_listener(self._listener)

    @property
    def current_state(self):
        return self.breaker.current_state.name

    @property
    def failure_count(self):
        return self.breaker.fail_counter

    async def run(self) -> list[Any]:
        try:
            return await self.breaker.call_async(Parallel(*self.tasks).run)
        except CircuitBreakerError as cbe:
            # Immediately fail
            await event_bus.emit(
                {"type": "circuit", "circuit": self, "state": "OPEN", "error": cbe}
            )
            raise


# --- Convenience Entrypoint -----------------------------------------------
async def run(task: Union[TaskRunner, Sequence, Parallel, CircuitGroup]) -> Any:
    """Top-level runner for any TaskRunner/Sequence/Parallel/CircuitGroup."""
    return await task.run()
