import pytest
from unittest.mock import MagicMock

from abm.api.capabilities import answerQuestion
from abm.api.core.registry import ServiceRegistry


def test_answer_question_with_history_injects_into_prompt():
    """
    Proves that when rolling conversation history is passed to answerQuestion,
    it is correctly formatted and injected into the prompt sent to the LLM.
    """
    # 1. Arrange: setup a mock registry
    registry = MagicMock(spec=ServiceRegistry)
    
    # Mock the router to return a conversational route
    from abm.orchestrator.router import Department
    router_mock = MagicMock()
    # It returns a RouterResult
    router_result_mock = MagicMock()
    router_result_mock.contract.department = Department.CONVERSATIONAL
    router_result_mock.confidence_hint = "high"
    router_result_mock.fallback_used = False
    router_mock.classify.return_value = router_result_mock
    registry.router = router_mock
    
    # Mock the embedder and controller (no hits needed for conversational test)
    registry.embedder.embed.return_value = [0.1, 0.2]
    
    controller_mock = MagicMock()
    # Query collection returns a mock QueryResult with empty documents
    query_result_mock = MagicMock()
    query_result_mock.ids = [[]]
    query_result_mock.documents = [[]]
    query_result_mock.metadatas = [[]]
    query_result_mock.distances = [[]]
    controller_mock.query_collection.return_value = query_result_mock
    registry.controller = controller_mock
    
    # Mock the gateway
    gateway_mock = MagicMock()
    response_mock = MagicMock()
    response_mock.text = "Blue is a great color!"
    gateway_mock.generate.return_value = response_mock
    registry.gateway = gateway_mock
    
    # 2. Act: Call answerQuestion with history
    history = [
        {"role": "user", "content": "My favorite color is blue."},
        {"role": "agent", "content": "That's a nice color!"}
    ]
    question = "What is my favorite color?"
    
    result = answerQuestion(question, registry=registry, history=history)
    
    # 3. Assert
    assert result.synthesis == "Blue is a great color!"
    assert result.degraded is False
    
    # Verify the prompt contained the history
    gateway_mock.generate.assert_called_once()
    called_prompt = gateway_mock.generate.call_args[0][0]
    
    assert "Recent Conversation History:" in called_prompt
    assert "User: My favorite color is blue." in called_prompt
    assert "Agent: That's a nice color!" in called_prompt
    assert "Question: What is my favorite color?" in called_prompt


def test_answer_question_never_writes_history_to_streams():
    """
    Proves that calling answerQuestion with or without history NEVER writes 
    anything to Stream C (or any collection) via the controller.
    """
    # 1. Arrange
    registry = MagicMock(spec=ServiceRegistry)
    
    from abm.orchestrator.router import Department
    router_result_mock = MagicMock()
    router_result_mock.contract.department = Department.SOFTWARE_ENGINEERING
    router_result_mock.confidence_hint = "high"
    router_result_mock.fallback_used = False
    registry.router.classify.return_value = router_result_mock
    registry.embedder.embed.return_value = [0.1, 0.2]
    
    query_result_mock = MagicMock()
    query_result_mock.ids = [["doc1"]]
    query_result_mock.documents = [["Some code snippet"]]
    query_result_mock.metadatas = [[{"source": "test.py"}]]
    query_result_mock.distances = [[0.1]]
    registry.controller.query_collection.return_value = query_result_mock
    
    gateway_mock = MagicMock()
    response_mock = MagicMock()
    response_mock.text = "Based on the code snippet..."
    gateway_mock.generate.return_value = response_mock
    registry.gateway = gateway_mock
    
    # 2. Act
    history = [{"role": "user", "content": "How does X work?"}]
    answerQuestion("Can you explain further?", registry=registry, history=history)
    
    # 3. Assert: The controller MUST NOT have add_document called
    registry.controller.add_document.assert_not_called()
    
    # Verify gateway generate was called with the history injected
    called_prompt = gateway_mock.generate.call_args[0][0]
    assert "User: How does X work?" in called_prompt
    assert "Question: Can you explain further?" in called_prompt
