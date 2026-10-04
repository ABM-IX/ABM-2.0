import pytest
from unittest.mock import MagicMock, patch

from abm.api.capabilities import reviewProject
from abm.api.core.registry import ServiceRegistry

def test_review_project_strict_grounding():
    # Arrange
    registry = MagicMock(spec=ServiceRegistry)
    registry.embedder.embed.return_value = [0.1, 0.2]

    # Mock the ChromaDB retrieval to return a single bug-ridden code chunk
    mock_hits = [
        {
            "id": "bad_code.py",
            "text": "global X\nX = 10\ndef calculate():\n    return X * 2",
            "distance": 0.1,
            "metadata": {"project": "test_project"}
        }
    ]
    
    with patch("abm.api.capabilities._flatten_query_hits", return_value=mock_hits):
        mock_response = MagicMock()
        mock_response.text = "Here are some suggestions..."
        registry.gateway.generate.return_value = mock_response

        # Act
        result = reviewProject("test_project", registry=registry)

        # Assert
        assert result.project_name == "test_project"
        assert not result.degraded
        assert len(result.hits) == 1
        assert result.synthesis == "Here are some suggestions..."

        # Verify the prompt contained the required grounding constraints and the actual code snippet
        registry.gateway.generate.assert_called_once()
        prompt = registry.gateway.generate.call_args[0][0]
        
        assert "CRITICAL ANTI-HALLUCINATION RULE: You must base your suggestions PURELY on the provided snippets" in prompt
        assert "global X" in prompt
        assert "bad_code.py" in prompt

def test_review_project_no_data():
    # Arrange
    registry = MagicMock(spec=ServiceRegistry)
    registry.embedder.embed.return_value = [0.1, 0.2]

    with patch("abm.api.capabilities._flatten_query_hits", return_value=[]):
        # Act
        result = reviewProject("empty_project", registry=registry)

        # Assert
        assert result.project_name == "empty_project"
        assert not result.degraded
        assert len(result.hits) == 0
        assert result.synthesis == "No code topology data found for this project in Stream A."
        
        # Ensure LLM was not called since there was no context
        registry.gateway.generate.assert_not_called()
