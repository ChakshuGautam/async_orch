import pytest
from async_orch import Sequence, Parallel, run  # Import global run
from tests.helpers import fetch_data, process_data, save_data


@pytest.mark.asyncio
async def test_simple_sequence_execution(capsys):
    """
    Tests a simple sequence of tasks using the new definition API.
    """
    # Define the sequence using raw functions and lambdas for arguments
    nested_pipeline_def = Sequence(
        lambda: fetch_data(1),  # Use lambda for args
        process_data,  # Receives output from fetch_data(1)
        save_data,  # Receives output from process_data
        name="TestNestedPipeline",
    )
    # Execute using the global run function
    result = await run(nested_pipeline_def)

    assert result == "DATA_1"  # save_data returns its input
    captured = capsys.readouterr()
    assert "Saved: DATA_1" in captured.out


@pytest.mark.asyncio
async def test_mixed_sequence_parallel_execution(capsys):
    """
    Tests a sequence containing a parallel block using the new definition API.
    """
    mixed_pipeline_def = Sequence(
        lambda: fetch_data(100),  # Output: "data_100"
        Parallel(
            # These run in parallel. process_data needs an input.
            # The previous step's output ("data_100") is NOT automatically passed to Parallel's tasks.
            # Parallel tasks are independent unless they are themselves sequences or designed to fetch.
            # For this test, let's assume they take fixed inputs as in the example.
            lambda: process_data("alpha"),
            lambda: process_data("beta"),
            name="TestProcessParallel",
        ),  # Output: ["ALPHA", "BETA"] (or ["BETA", "ALPHA"])
        # The next task in sequence (save_data) receives the list from Parallel.
        save_data,
        name="TestMixedPipeline",
    )
    result = await run(mixed_pipeline_def)

    assert isinstance(result, list)
    assert len(result) == 2
    assert "ALPHA" in result
    assert "BETA" in result

    captured = capsys.readouterr()
    assert "Saved: " in captured.out
    # The exact string representation of the list might vary in order
    assert "['ALPHA', 'BETA']" in captured.out or "['BETA', 'ALPHA']" in captured.out


@pytest.mark.asyncio
async def test_sequence_with_no_tasks():
    """Tests Sequence flow with no tasks using the new definition API."""
    empty_sequence_def = Sequence(name="TestEmptySequence")
    result = await run(empty_sequence_def)
    assert result == []


@pytest.mark.asyncio
async def test_sequence_with_one_task():
    """Tests Sequence flow with a single task using the new definition API."""
    single_task_sequence_def = Sequence(
        lambda: fetch_data(1), name="TestSingleTaskSequence"  # Use lambda for args
    )
    result = await run(single_task_sequence_def)
    assert result == "data_1"
