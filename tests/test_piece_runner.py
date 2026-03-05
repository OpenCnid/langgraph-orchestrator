"""Tests for the piece execution engine — loading, validation, execution, skills, recovery."""

import hashlib
import json

import pytest

from src.atlas import Atlas
from src.lib.models import Conclusion, Piece, PieceStatus, PieceType
from src.lib.piece_runner import (
    ExecutionState,
    execute_piece,
    load_piece_components,
    load_skills_for_decision,
    validate_piece,
)


def _make_forward_piece(
    piece_id: str = "test_piece",
    title: str = "Test Piece",
    status: PieceStatus = PieceStatus.ACTIVE,
    connections: list[str] | None = None,
) -> Piece:
    content = f"""# {title}

**Type:** forward
**Status:** {status.value}
**Connections:** [{', '.join(connections or [])}]

A test workflow piece.

```mermaid
graph TD
    A[Start] --> B{{Check input}}
    B -->|Valid| C[Process]
    B -->|Invalid| D[Report error]
    C --> E[Return result]
```
"""
    return Piece(
        id=piece_id,
        title=title,
        type=PieceType.FORWARD,
        status=status,
        connections=connections or [],
        content=content,
    )


def _make_skill_piece(
    piece_id: str = "test_skill",
    title: str = "Test Skill",
) -> Piece:
    content = f"""# {title}

**Type:** skill
**Status:** active

Skill for making decisions about test data.

## Heuristics
- Always prefer complete data over partial
- Flag ambiguous results
"""
    return Piece(
        id=piece_id,
        title=title,
        type=PieceType.SKILL,
        status=PieceStatus.ACTIVE,
        content=content,
    )


def _mock_llm(response: str) -> callable:
    """Create a mock LLM that returns a fixed response."""
    def llm_fn(system_prompt: str, user_prompt: str) -> str:
        return response
    return llm_fn


def _mock_llm_json(
    summary: str = "Workflow completed",
    status: str = "success",
    key_outputs: dict | None = None,
    diagnostics: str | None = None,
) -> callable:
    """Create a mock LLM that returns a valid JSON conclusion."""
    result = {
        "summary": summary,
        "status": status,
        "key_outputs": key_outputs or {},
        "diagnostics": diagnostics,
    }
    return _mock_llm(json.dumps(result))


def _deterministic_embed(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec: list[float] = []
    for i in range(1536):
        byte_idx = i % len(h)
        bit_idx = i % 8
        val = ((h[byte_idx] >> bit_idx) & 1) * 2.0 - 1.0
        vec.append(val)
    return vec


class TestPieceValidation:
    """Validate pieces before execution — active status, mermaid required."""

    def test_active_piece_validates(self) -> None:
        piece = _make_forward_piece()
        validate_piece(piece)  # should not raise

    def test_draft_piece_rejected(self) -> None:
        piece = _make_forward_piece(status=PieceStatus.DRAFT)
        with pytest.raises(ValueError, match="draft"):
            validate_piece(piece)

    def test_archived_piece_rejected(self) -> None:
        piece = _make_forward_piece(status=PieceStatus.ARCHIVED)
        with pytest.raises(ValueError, match="archived"):
            validate_piece(piece)

    def test_forward_piece_without_mermaid_rejected(self) -> None:
        piece = Piece(
            id="no_mermaid",
            title="No Diagram",
            type=PieceType.FORWARD,
            status=PieceStatus.ACTIVE,
            content="# No Diagram\n\nJust prose, no mermaid.",
        )
        with pytest.raises(ValueError, match="no mermaid"):
            validate_piece(piece)

    def test_skill_without_mermaid_validates(self) -> None:
        piece = _make_skill_piece()
        validate_piece(piece)  # skills don't need mermaid


class TestPieceLoading:
    """Load piece content into executable components."""

    def test_load_components_extracts_mermaid(self) -> None:
        piece = _make_forward_piece()
        components = load_piece_components(piece)
        assert components["mermaid"] is not None
        assert "graph TD" in components["mermaid"]

    def test_load_components_extracts_prose(self) -> None:
        piece = _make_forward_piece()
        components = load_piece_components(piece)
        assert "A test workflow piece" in components["prose"]

    def test_load_components_includes_metadata(self) -> None:
        piece = _make_forward_piece(piece_id="lookup", title="Record Lookup")
        components = load_piece_components(piece)
        assert components["metadata"]["id"] == "lookup"
        assert components["metadata"]["title"] == "Record Lookup"
        assert components["metadata"]["type"] == "forward"

    def test_load_components_full_content(self) -> None:
        piece = _make_forward_piece()
        components = load_piece_components(piece)
        assert components["full_content"] == piece.content

    def test_skill_has_no_mermaid(self) -> None:
        piece = _make_skill_piece()
        components = load_piece_components(piece)
        assert components["mermaid"] is None
        assert "Heuristics" in components["prose"]


class TestPieceExecution:
    """Execute a piece via LLM and get a Conclusion."""

    def test_successful_execution(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Found 3 records", status="success")
        result = execute_piece(piece, {"query": "test"}, llm_fn=llm_fn)
        assert result.status == "success"
        assert result.summary == "Found 3 records"

    def test_failed_execution(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(
            summary="Invalid input format",
            status="failed",
            diagnostics="Expected UUID, got 'abc'",
        )
        result = execute_piece(piece, {"id": "abc"}, llm_fn=llm_fn)
        assert result.status == "failed"
        assert "Invalid input" in result.summary

    def test_partial_execution(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(
            summary="Processed 2 of 5 records",
            status="partial",
            key_outputs={"processed": 2, "total": 5},
        )
        result = execute_piece(piece, {"records": [1, 2, 3, 4, 5]}, llm_fn=llm_fn)
        assert result.status == "partial"
        assert result.key_outputs["processed"] == 2

    def test_non_json_llm_output_treated_as_summary(self) -> None:
        """If LLM returns plain text instead of JSON, treat it as a success summary."""
        piece = _make_forward_piece()
        llm_fn = _mock_llm("The workflow completed and found 3 results.")
        result = execute_piece(piece, {}, llm_fn=llm_fn)
        assert result.status == "success"
        assert "3 results" in result.summary

    def test_llm_exception_returns_failed(self) -> None:
        piece = _make_forward_piece()

        def failing_llm(system: str, user: str) -> str:
            raise RuntimeError("API connection failed")

        result = execute_piece(piece, {}, llm_fn=failing_llm)
        assert result.status == "failed"
        assert "API connection failed" in (result.diagnostics or "")

    def test_empty_inputs_works(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Done")
        result = execute_piece(piece, {}, llm_fn=llm_fn)
        assert result.status == "success"

    def test_key_outputs_preserved(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(
            summary="Found record",
            key_outputs={"record_id": "R123", "status": "active"},
        )
        result = execute_piece(piece, {"id": "R123"}, llm_fn=llm_fn)
        assert result.key_outputs["record_id"] == "R123"


class TestConclusionContract:
    """Conclusions must be structured objects — no leaking of execution internals."""

    def test_conclusion_has_required_fields(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Done", status="success")
        result = execute_piece(piece, {}, llm_fn=llm_fn)
        assert hasattr(result, "summary")
        assert hasattr(result, "status")
        assert hasattr(result, "key_outputs")
        assert hasattr(result, "diagnostics")

    def test_execution_trace_not_in_conclusion(self) -> None:
        """Execution trace stays inside the engine — not exposed in the conclusion."""
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Done")
        result = execute_piece(piece, {}, llm_fn=llm_fn)
        # Conclusion should not contain execution trace
        assert not hasattr(result, "execution_trace")
        assert not hasattr(result, "node_outputs")


class TestSkillLoading:
    """Skills load into context for LLM-bridged decision nodes."""

    def test_connected_skills_loaded(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        skill = _make_skill_piece(piece_id="interp_skill", title="Interpretation")
        atlas.add_piece(skill)

        piece = _make_forward_piece(connections=["interp_skill"])
        skills_text = load_skills_for_decision(piece, atlas)
        assert "Interpretation" in skills_text
        assert "Heuristics" in skills_text

    def test_no_atlas_returns_empty(self) -> None:
        piece = _make_forward_piece()
        skills_text = load_skills_for_decision(piece, None)
        assert skills_text == ""

    def test_skills_included_in_execution(self) -> None:
        """When a piece has connected skills, they're included in the LLM prompt."""
        atlas = Atlas(embed_fn=_deterministic_embed)
        skill = _make_skill_piece(piece_id="test_skill", title="Decision Skill")
        atlas.add_piece(skill)

        piece = _make_forward_piece(connections=["test_skill"])
        atlas.add_piece(piece)

        # Track what the LLM receives
        received_prompts: list[str] = []

        def tracking_llm(system: str, user: str) -> str:
            received_prompts.append(system)
            return json.dumps({"summary": "Done", "status": "success"})

        execute_piece(piece, {}, llm_fn=tracking_llm, atlas=atlas)
        # The system prompt should include the skill content
        assert len(received_prompts) == 1
        assert "Decision Skill" in received_prompts[0]

    def test_archived_skills_not_loaded(self) -> None:
        atlas = Atlas(embed_fn=_deterministic_embed)
        skill = _make_skill_piece(piece_id="old_skill", title="Archived Skill")
        skill.status = PieceStatus.ARCHIVED
        atlas.add_piece(skill)

        piece = _make_forward_piece(connections=["old_skill"])
        skills_text = load_skills_for_decision(piece, atlas)
        assert skills_text == ""


class TestRecoveryHooks:
    """Recovery hooks fire on failed/escalated conclusions."""

    def test_recovery_hook_triggered_on_failure(self) -> None:
        piece = _make_forward_piece()
        call_count = 0

        def counting_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({
                    "summary": "Failed",
                    "status": "failed",
                    "diagnostics": "Data source unavailable",
                })
            return json.dumps({"summary": "Recovered", "status": "success"})

        def recovery_hook(state: ExecutionState, output: str) -> Conclusion | None:
            return Conclusion(summary="Try alternative source", status="partial")

        result = execute_piece(
            piece, {}, llm_fn=counting_llm, recovery_hook=recovery_hook
        )
        assert result.status == "success"
        assert call_count == 2

    def test_retry_limit_enforced(self) -> None:
        piece = _make_forward_piece()

        def always_fail_llm(system: str, user: str) -> str:
            return json.dumps({
                "summary": "Failed",
                "status": "failed",
                "diagnostics": "Persistent error",
            })

        def always_recover(state: ExecutionState, output: str) -> Conclusion | None:
            return Conclusion(summary="Try again", status="partial")

        result = execute_piece(
            piece, {}, llm_fn=always_fail_llm, recovery_hook=always_recover,
            max_retries=2,
        )
        assert result.status == "escalated"
        assert "Retry limit" in result.summary or "exceeded" in (result.diagnostics or "")

    def test_no_recovery_hook_returns_failure_directly(self) -> None:
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Error", status="failed", diagnostics="boom")
        result = execute_piece(piece, {}, llm_fn=llm_fn)
        assert result.status == "failed"

    def test_recovery_hook_returns_none_no_retry(self) -> None:
        """If recovery hook returns None, no retry — return the original conclusion."""
        piece = _make_forward_piece()
        llm_fn = _mock_llm_json(summary="Error", status="failed")

        def noop_hook(state: ExecutionState, output: str) -> Conclusion | None:
            return None

        result = execute_piece(piece, {}, llm_fn=llm_fn, recovery_hook=noop_hook)
        assert result.status == "failed"


class TestExecutionState:
    """Per-execution state tracking."""

    def test_execution_state_isolated(self) -> None:
        s1 = ExecutionState(piece_id="a", inputs={"x": 1})
        s2 = ExecutionState(piece_id="b", inputs={"y": 2})
        s1.node_outputs["step1"] = "result1"
        assert "step1" not in s2.node_outputs

    def test_execution_state_tracks_trace(self) -> None:
        state = ExecutionState(piece_id="test", inputs={})
        state.execution_trace.append("node_A")
        state.execution_trace.append("node_B")
        assert state.execution_trace == ["node_A", "node_B"]
