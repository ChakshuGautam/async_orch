# API Naming and Clarity Improvements Checklist

## Class and Method Naming
- [x] Rename classes with descriptive CapWords (e.g., `TaskRun` to `TaskRunner` or `TaskExecution`, `MultiprocessTaskRun` to `MultiprocessTaskRunner`).
- [x] Use snake_case for method and variable names (e.g., `getResult()` to `get_result()`, `IsRunning()` to `is_running()`, `StopTask()` to `stop_task()`).

## Parameter Naming and Context
- [x] Clarify parameter names and add context (e.g., `retries` to `max_retries`, `retry_sleep_time` to `retry_delay_seconds` or `retry_interval`, `parallelism` to `max_workers` or `concurrency`).

## Terminology and Role Names
- [x] Consolidate terminology and role names (e.g., use "task" consistently instead of mixing "job" or "activity").
- [ ] Rename runner classes consistently (e.g., `SequentialTaskRunner` instead of `SequentialTaskRun`).
- [ ] Refactor `Sequence` and `Parallel` to accept raw callable functions directly, potentially making `TaskRunner` an internal implementation detail.

## Abbreviations
- [ ] Avoid unclear abbreviations (e.g., `thr` to `thread` or `executor`, `ctx` to `context`, `conf` to `config`).

## Public API Methods and Signatures
- [ ] Align task handles with Python Future API (e.g., `.result()` instead of `.get_result()`, `.cancel()` instead of `.stop()`, `.done()` or `.running()` instead of `.is_running()`).
- [ ] Use clear keyword-only arguments for flags (e.g., `run(tasks, *, blocking=True)` instead of `run(tasks, True)`).
- [ ] Simplify overloaded methods or separate concerns (e.g., `run_async()` and `run_sync()` instead of a single `run()` method handling both).
- [ ] Group related configuration parameters into a configuration object or named tuple (e.g., `RetryConfig(max_retries, delay_seconds)`).
- [ ] Clarify public entry-point names with verbs reflecting their action (e.g., `execute()`, `submit()`, or `start()` instead of ambiguous terms; `orchestrate()` or `dispatch_tasks()` instead of a generic `run()`).
