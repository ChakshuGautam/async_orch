# API Refactoring: Definition/Execution Separation

## Design Rationale

The primary goal of this refactoring is to enhance the clarity, usability, and consistency of the `async_orch` library's public API. By separating the **definition** of task workflows (how tasks are structured in sequences, parallel groups, or under circuit breakers) from their **execution** (the machinery that actually runs them), we aim to achieve several benefits:

1.  **Improved User Experience:** Users can focus on declaratively defining their workflows using simple, intuitive classes (`Sequence`, `Parallel`, `CircuitDefinition`) and their own Python functions. The complexities of task execution are abstracted away.
2.  **Clearer Abstraction:** Internal components responsible for running tasks (e.g., `_TaskRunner`, `_SequentialTaskRunner`) will be hidden from the public API, reducing cognitive load for the library user.
3.  **Enhanced API Consistency:** The pattern of "define then run" will be applied uniformly across all orchestration types (sequential, parallel, circuit-controlled), making the library easier to learn and use.
4.  **Reinforced Task Atomicity:** This design emphasizes that user-provided functions are the atomic units of work, and the library provides powerful tools for composing and orchestrating these units.

This shift moves towards a more declarative style, where users specify *what* they want to achieve, and the library handles *how* to achieve it efficiently and robustly.

## Core Library Refactoring (`async_orch/__init__.py`)

1.  **Internalize `TaskRunner`:**
    *   [x] Rename `TaskRunner` to `_TaskRunner`.
    *   [x] Update all internal usages of `TaskRunner` to `_TaskRunner`.

2.  **Refactor `Sequence` Workflow:**
    *   [x] Create new public class `Sequence` (for definition).
        *   Constructor accepts `*steps: Union[TaskFn, "Sequence", "Parallel"]`.
        *   No `run()` method. Stores steps.
    *   [x] Rename existing `SequentialTaskRunner` to `_SequentialTaskRunner` (internal executor).
        *   Constructor accepts an instance of the new `Sequence` class.
        *   Keeps the `run()` method logic, adapting it to use the `Sequence` definition and `_TaskRunner` for individual function steps.

3.  **Refactor `Parallel` Workflow:**
    *   [x] Create new public class `Parallel` (for definition).
        *   Constructor accepts `*tasks: Union[TaskFn, "Sequence", "Parallel"]` and `max_workers`, `name`.
        *   No `run()` method. Stores tasks and config.
    *   [x] Rename existing `ParallelTaskRunner` to `_ParallelTaskRunner` (internal executor).
        *   Constructor accepts an instance of the new `Parallel` class.
        *   Keeps the `run()` method logic, adapting it to use the `Parallel` definition and `_TaskRunner` for individual function tasks.

4.  **Refactor `CircuitGroup` Workflow:**
    *   [x] Create new public class `CircuitDefinition` (for definition).
        *   Constructor accepts `*tasks: Union[TaskFn, "Sequence", "Parallel"]` and circuit breaker parameters (`fail_max`, `reset_timeout`, `name`).
        *   No `run()` method. Stores tasks and config.
    *   [x] Rename existing `CircuitGroupTaskRunner` to `_CircuitGroupTaskRunner` (internal executor).
        *   Constructor accepts an instance of the new `CircuitDefinition` class.
        *   Keeps the `run()` method logic, adapting it to use the `CircuitDefinition` and `_TaskRunner` for individual function tasks.

5.  **Adapt Top-Level `run()` Function:**
    *   [x] Modify the global `run(task: ...)` function.
        *   Its `task` parameter type hint will change to `Union[_TaskRunner, Sequence, Parallel, CircuitDefinition]`.
        *   It will need to instantiate the correct internal runner based on the type of the input definition object (e.g., if `task` is `Sequence`, call `_SequentialTaskRunner(task).run()`).

6.  **Update Type Hints and Cross-References:**
    *   [x] Review and update all type hints in `async_orch/__init__.py` to reflect these new class names and relationships.

## Update Examples and Test Cases

7.  **Update Examples:**
    *   [x] Modify `examples/example.py` to use the new definition-based API.
        *   Update imports.
        *   Update instantiation logic (use `Sequence`, `Parallel`, `CircuitDefinition` with raw functions).
        *   Ensure examples still demonstrate core functionalities correctly.

8.  **Update Test Cases:**
    *   [x] Modify all relevant files in `tests/` (e.g., `test_sequence.py`, `test_parallel.py`, `test_circuit_breaker.py`, etc.) to align with the new API and internal class structure.
        *   Update imports and instantiation logic.
        *   Adapt tests that targeted the public API of old runner classes.
        *   Ensure test coverage for new public definition classes and internal runner logic.
