import pytest
from async_orch import TaskRunner, Sequence, Parallel
from tests.helpers import fetch_data, process_data, save_data


@pytest.mark.asyncio
async def test_simple_sequence_execution(capsys):
    """
    Tests a simple sequence of tasks.
    Corresponds to example_nested_sequence.
    """
    nested_pipeline = Sequence(
        TaskRunner(fetch_data, 1, name="Fetch1"),
        TaskRunner(process_data, name="Process1"),
        TaskRunner(save_data, name="Save1"),
        name="TestNestedPipeline",
    )
    result = await nested_pipeline.run()

    # save_data in helpers.py prints and returns the processed data
    assert result == "DATA_1"
    captured = capsys.readouterr()
    assert "Saved: DATA_1" in captured.out


@pytest.mark.asyncio
async def test_mixed_sequence_parallel_execution(capsys):
    """
    Tests a sequence containing a parallel block.
    Corresponds to example_mixed_pipeline.
    """
    mixed_pipeline = Sequence(
        TaskRunner(fetch_data, 100, name="Fetch100"),  # Output: "data_100"
        Parallel(  # Input: "data_100" (but tasks inside don't use it)
            TaskRunner(process_data, "alpha", name="ProcessAlpha"),  # Output: "ALPHA"
            TaskRunner(process_data, "beta", name="ProcessBeta"),  # Output: "BETA"
            name="TestProcessParallel",
        ),  # Output: ["ALPHA", "BETA"] (or ["BETA", "ALPHA"])
        TaskRunner(save_data, name="SaveMixedSummary"),  # Input: ["ALPHA", "BETA"]
        name="TestMixedPipeline",
    )
    result = await mixed_pipeline.run()

    # save_data will be called with the list from Parallel
    # and it returns this list.
    assert isinstance(result, list)
    assert len(result) == 2
    assert "ALPHA" in result
    assert "BETA" in result

    captured = capsys.readouterr()
    # Check that save_data printed the list
    assert "Saved: " in captured.out
    assert "['ALPHA', 'BETA']" in captured.out or "['BETA', 'ALPHA']" in captured.out


@pytest.mark.asyncio
async def test_sequence_with_no_tasks():
    """Tests Sequence flow with no tasks."""
    seq_flow = Sequence(name="TestEmptySequence")
    result = await seq_flow.run()
    assert result == []  # An empty sequence returns an empty list


@pytest.mark.asyncio
async def test_sequence_with_one_task():
    """Tests Sequence flow with a single task."""
    seq_flow = Sequence(
        TaskRunner(fetch_data, 1, name="FetchSingle"), name="TestSingleTaskSequence"
    )
    result = await seq_flow.run()
    assert result == "data_1"
