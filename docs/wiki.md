# async_orch Wiki

## 1. Introduction

`async_orch` is a Python library designed for building and managing asynchronous task pipelines. It provides a flexible framework to define individual tasks, sequence them, run them in parallel with concurrency controls, and apply resilience patterns like circuit breakers. The library is built on `asyncio` to handle non-blocking operations efficiently.

## 2. Core Components & Concepts

The library revolves around a few key components:

- **Tasks (Functions)**: The fundamental units of work are now regular Python functions (sync or async). The library internally wraps these in an execution mechanism when they are part of a `Sequence`, `Parallel`, or `CircuitDefinition`.
  - The internal runner handles state tracking (`TaskState`: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `RETRYING`, `CANCELLED`).
  - State transitions and results/errors are communicated via the `EventBus`.

- **`EventBus`**:

  - A global publish-subscribe mechanism.
  - Tasks, CircuitGroups, and other components emit events (e.g., state changes, errors, results) to this bus.
  - Allows for decoupled monitoring, logging, or other reactions to workflow events.

- **`Sequence`**:

  - A composite structure that executes a series of steps (functions, other Sequences, or Parallels) one after another.
  - The output of one step is passed as input to the next, if the next step's function accepts arguments.
  - If any step fails, the sequence typically stops and propagates the error.
  - Returns the result of the last successfully completed step in the sequence.

- **`Parallel`**:

  - A composite structure that executes multiple tasks (functions, Sequences, or other Parallels) concurrently.
  - Supports an optional `max_workers` parameter to control the maximum number of tasks running at the same time.
  - Waits for all tasks to complete and returns a list of their results. The order of results corresponds to the order of tasks defined.

- **`CircuitDefinition`**: (Replaces `CircuitGroup`)

  - A definition that wraps one or more tasks (functions, Sequences, or Parallels, typically run as a parallel group internally) with a circuit breaker pattern, utilizing the `aiobreaker` library.
  - Helps prevent repeated calls to services or tasks that are failing.
  - Monitors failures and "opens" the circuit if the failure threshold (`fail_max`) is reached within a certain time, preventing further calls for a `reset_timeout` period.
  - Emits events for circuit state changes (e.g., `OPEN`, `CLOSED`, `HALF_OPEN`).

- **`TaskState`**:
  - An `Enum` defining the possible lifecycle states of a `Task`:
    - `PENDING`: Task is created but not yet started.
    - `RUNNING`: Task is currently executing.
    - `SUCCEEDED`: Task completed successfully.
    - `FAILED`: Task terminated with an error.
    - `RETRYING`: Task failed and is being retried (often part of a custom retry policy).
    - `CANCELLED`: Task execution was cancelled.

## 3. Key Features

- **Asynchronous by Design**: Built on Python's `asyncio` library, enabling efficient handling of I/O-bound operations and concurrent task execution.
- **Composability**: Composite structures (`Sequence`, `Parallel`, `CircuitDefinition`) can be nested to create complex and sophisticated workflows.
- **State Management & Observability**: The `EventBus` provides a centralized way to monitor the state and progress of individual tasks (via internal runners) and circuit breakers, facilitating logging, metrics collection, and real-time feedback.
- **Extensible Execution Policies**: While `TaskRunner` is internal, the concept of applying policies like retries still exists. This is typically done by wrapping the task function itself (e.g., with a decorator like `backoff`) before passing it to a `Sequence`, `Parallel`, or `CircuitDefinition`.

## 4. How to Use (Illustrated with examples from `examples/example.py`)

### Defining Basic Tasks (Functions)

Tasks are now just Python functions. Arguments are passed using lambdas for the first task in a sequence or for all tasks in a parallel group if they don't depend on prior outputs.

```python
import asyncio

# Asynchronous task
async def fetch_data(id_val: int): # Renamed id to id_val to avoid conflict
    await asyncio.sleep(0.5)
    return f"data_{id_val}"

# Synchronous task
def process_data(data: str) -> str:
    return data.upper()
```

### Creating a `Sequence`

Execute functions one after another. The output of one is passed to the next.

```python
from async_orch import Sequence, run 
# ... (fetch_data, process_data, save_data definitions) ...

# Assume save_data is defined:
# async def save_data(data_to_save: str): print(f"Saving {data_to_save}")

user_profile_pipeline = Sequence(
    lambda: fetch_data(101),    # First task with arguments via lambda
    process_data,               # Receives output of fetch_data
    # save_data,                # Receives output of process_data
    name="UserProfileWorkflow"
)

# To run:
# result_of_last_task = await run(user_profile_pipeline)
```

### Creating a `Parallel` Execution

Execute functions concurrently, optionally limiting concurrency.

```python
from async_orch import Parallel, run 
# ... (fetch_data definition) ...

parallel_fetch = Parallel(
    lambda: fetch_data(10),
    lambda: fetch_data(20),
    lambda: fetch_data(30),
    max_workers=2, # Optional: Max 2 tasks run at once
    name="SimpleParallelFetch"
)
# To run:
# results_list = await run(parallel_fetch)
# results_list will be: ['data_10', 'data_20', 'data_30'] (order maintained)
```

### Implementing Retries

Retries are typically implemented by wrapping the task function itself, for example, using a library like `backoff`.

```python
from async_orch import Sequence, run, event_bus, TaskState # TaskState for event logging
import backoff
import asyncio

# Example flaky task
async def flaky_task():
    if asyncio.shield(asyncio.sleep(0)): # Dummy condition
        raise ValueError("Simulated network error")
    return "Success!"

# Event handler for retries (optional, for logging)
async def on_retry_event(details):
    # Note: 'task' in event will be an internal runner instance.
    # You might need to map it back to your original function if needed for logging.
    print(f"RETRYING: Task {details.get('target', {}).__name__}, attempt {details.get('tries')}, waiting {details.get('wait'):.2f}s")
    # Emitting a custom event or using event_bus if the internal runner emits retry events
    # await event_bus.emit(...) # If you want to use the main event bus

@backoff.on_exception(
    backoff.expo,
    Exception, # Catch all exceptions for retry
    max_tries=3,
    on_backoff=lambda details: asyncio.create_task(on_retry_event(details)) # Ensure handler is async if it awaits
)
async def flaky_task_with_retry():
    return await flaky_task()

# Use the wrapped task in a sequence
retry_pipeline = Sequence(flaky_task_with_retry, name="RetryFlaky")

# To run:
# try:
#     result = await run(retry_pipeline)
# except Exception as e:
#     print(f"Flaky task ultimately failed: {e}")
```

### Using `CircuitDefinition`

Protect your system from cascading failures.

```python
from async_orch import CircuitDefinition, run # Assuming fetch_data, process_data are defined
# ... (fetch_data, process_data definitions) ...

# Tasks for the circuit breaker are defined as a list/tuple.
# They will typically run in parallel under the breaker.
circuit_protected_tasks = CircuitDefinition(
    lambda: fetch_data(201),
    lambda: process_data("raw_circuit_data"), # Example independent task
    fail_max=2,        # Open circuit after 2 failures
    reset_timeout=10,  # Try to close circuit after 10 seconds
    name="DemoCircuit"
)

# To run:
# from aiobreaker import CircuitBreakerError # Import for catching specific error
# try:
#     results = await run(circuit_protected_tasks) # Returns a list of results if successful
# except CircuitBreakerError as e:
#     print(f"Circuit breaker triggered: {e}")
# except Exception as e:
#     print(f"Other error in circuit protected tasks: {e}")
```

### Subscribing to the `EventBus`

Monitor task and circuit events.

```python
# From examples/example.py
from async_orch import event_bus # Assuming TaskState is also imported if used in event
import asyncio

async def log_event(event): # Made async to match EventBus.emit
    print(f"EVENT: {event}")

# Subscribe the logger
# The lambda creates an asyncio.create_task for fire-and-forget
event_bus.subscribe(lambda e: asyncio.create_task(log_event(e)))
```

When a task changes state, an event like this might be emitted (note: `task` refers to an internal runner object):
`{'type': 'task', 'task': <async_orch._TaskRunner object at ...>, 'state': TaskState.RUNNING}`
`{'type': 'task', 'task': <async_orch._TaskRunner object at ...>, 'state': TaskState.SUCCEEDED, 'result': 'data_1'}`

For circuit breakers (using `CircuitDefinition`):
`{'type': 'circuit', 'circuit_definition_name': 'DemoCircuit', 'old_state': 'CLOSED', 'new_state': 'OPEN'}` (State names are strings)

### Top-level Runner

The `async_orch.run()` function provides a convenient way to execute any top-level `Sequence`, `Parallel`, or `CircuitDefinition`.

```python
from async_orch import run

# Assuming 'my_main_workflow' is a Sequence, Parallel, or CircuitDefinition instance
# await run(my_main_workflow)
```

## 5. Codebase Structure

- **`async_orch/__init__.py`**: This file contains the core framework classes:

  - `EventBus`: Manages event subscriptions and emissions.
  - `TaskState`: Enum for task lifecycle states.
  - `Sequence`: For sequential execution of tasks/definitions.
  - `Parallel`: For concurrent execution of tasks/definitions.
  - `CircuitDefinition`: Defines a group of tasks protected by a circuit breaker.
  - `run()`: A top-level convenience function to execute any workflow component.
  - Internal classes like `_TaskRunner`, `_SequentialTaskRunner`, `_ParallelTaskRunner`, `_CircuitGroupTaskRunner` handle the actual execution logic.

- **`examples/example.py`**: This file provides practical usage examples of the `async_orch` library. It demonstrates:
  - Defining various types of task functions.
  - Constructing sequences and parallel groups using the new API.
  - Implementing a retry mechanism for a flaky task using `backoff`.
  - Using a `CircuitDefinition`.
  - Subscribing to the event bus for logging.
  - Running a mixed pipeline of sequences and parallel groups.

## 6. Running the Examples

To see the `async_orch` library in action, you can run the `examples/example.py` script:

```bash
python examples/example.py
```

This will execute all the defined examples and print event logs and results to the console.
