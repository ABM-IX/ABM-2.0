import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.api.capabilities import answerQuestion, AnswerResult
from abm.api.core.registry import ServiceRegistry
from abm.memory.chroma_controller import ChromaController, COLLECTION_AMBIENT_TELEMETRY

class TestClient01Conversational(unittest.TestCase):
    def setUp(self):
        self.registry = MagicMock(spec=ServiceRegistry)
        self.registry.gateway = MagicMock()
        self.registry.router = MagicMock()
        self.registry.embedder = MagicMock()
        self.registry.controller = MagicMock()

    def test_fast_conversational_pre_check(self):
        """Plain conversational greetings return warm response without router/embedder/gateway calls."""
        result = answerQuestion("hello", registry=self.registry)
        self.assertIsInstance(result, AnswerResult)
        self.assertEqual(result.department, "conversational")
        self.assertIn("Hey! I'm ABM 2.0", result.synthesis)
        self.assertFalse(result.degraded)
        self.registry.router.classify.assert_not_called()
        self.registry.gateway.generate.assert_not_called()

    def test_conversational_dynamic_routing(self):
        """Complex conversational prompts route dynamically through gateway."""
        # Setup mock router classification
        mock_router_result = MagicMock()
        from abm.orchestrator.departments import Department
        mock_router_result.contract.department = Department.CONVERSATIONAL
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        self.registry.router.classify.return_value = mock_router_result

        # Setup mock retrieval
        self.registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [["123"]]
        mock_qr.documents = [["ABM 2.0 acts as my persistent personal cognitive layer..."]]
        mock_qr.metadatas = [[{"owner": "ABM"}]]
        mock_qr.distances = [[0.1]]
        self.registry.controller.query_collection.return_value = mock_qr

        # Setup mock gateway synthesis
        mock_response = MagicMock()
        mock_response.text = "Hello! I am ABM 2.0."
        self.registry.gateway.generate.return_value = mock_response

        # Test with a complex conversational prompt that bypasses simple regex greetings
        result = answerQuestion("How are you handling complex project flows today?", registry=self.registry)

        self.assertIsInstance(result, AnswerResult)
        self.assertEqual(result.department, "conversational")
        self.assertEqual(result.synthesis, "Hello! I am ABM 2.0.")
        
        # Prove router WAS called
        self.registry.router.classify.assert_called_once_with("How are you handling complex project flows today?")
        self.registry.embedder.embed.assert_any_call("How are you handling complex project flows today?")

    def test_complex_identity_question_routes_normally(self):
        # Setup mock router classification
        mock_router_result = MagicMock()
        from abm.orchestrator.departments import Department
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        self.registry.router.classify.return_value = mock_router_result

        # Setup mock retrieval
        self.registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [["123"]]
        mock_qr.documents = [["ABM 2.0 acts as my persistent personal cognitive layer..."]]
        mock_qr.metadatas = [[{"owner": "ABM"}]]
        mock_qr.distances = [[0.1]]
        self.registry.controller.query_collection.return_value = mock_qr

        # Setup mock gateway synthesis
        mock_response = MagicMock()
        mock_response.text = "My mission is to act as a persistent personal cognitive layer."
        self.registry.gateway.generate.return_value = mock_response

        # Test with a deeper identity question
        result = answerQuestion("what is your mission?", registry=self.registry)

        self.assertIsInstance(result, AnswerResult)
        self.assertEqual(result.department, "software_engineering")
        
        # Prove router WAS called
        self.registry.router.classify.assert_called_once_with("what is your mission?")
        self.registry.embedder.embed.assert_any_call("what is your mission?")
        self.registry.gateway.generate.assert_called_once()
        self.assertIn("ONLY the facts explicitly present in the provided context", self.registry.gateway.generate.call_args[0][0])

    def test_stream_c_no_chroma_store_pollution(self):
        controller = ChromaController(in_memory=False, persist_directory="memory/chroma_store")
        collection = controller.get_collection(COLLECTION_AMBIENT_TELEMETRY)
        all_data = collection.get(include=["documents"])
        documents = all_data.get("documents", [])
        
        for text in documents:
            self.assertNotIn("memory/chroma_store", text)
            self.assertNotIn("memory\\chroma_store", text)

    def test_strict_grounding_no_hallucinated_expansions(self):
        # Setup mock router classification to hit software_engineering (non-conversational)
        mock_router_result = MagicMock()
        from abm.orchestrator.departments import Department
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        self.registry.router.classify.return_value = mock_router_result

        # Setup mock retrieval providing ONLY minimal context without expansions
        self.registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [["123"]]
        mock_qr.documents = [["ABM is the digital layer."]]
        mock_qr.metadatas = [[{"owner": "ABM"}]]
        mock_qr.distances = [[0.1]]
        self.registry.controller.query_collection.return_value = mock_qr

        # We will use the actual prompt logic that will be passed to gateway.generate
        # to ensure it strictly restricts the model. We can assert that the prompt
        # contains the CRITICAL RESTRICTION clause.
        mock_response = MagicMock()
        mock_response.text = "ABM is the digital layer."
        self.registry.gateway.generate.return_value = mock_response

        answerQuestion("what is the mission of the system?", registry=self.registry)
        
        # Verify prompt has the required strict grounding language
        self.registry.gateway.generate.assert_called_once()
        prompt_used = self.registry.gateway.generate.call_args[0][0]
        self.assertIn("CRITICAL ANTI-HALLUCINATION RULE:", prompt_used)
        self.assertIn("STRICTLY FORBIDDEN", prompt_used)

    def test_identity_question_broad_phrasings(self):
        # We test that the extractive identity branch is taken for multiple phrasings
        mock_router_result = MagicMock()
        from abm.orchestrator.departments import Department
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        self.registry.router.classify.return_value = mock_router_result

        self.registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [["123"]]
        mock_qr.documents = [["(identity doc)"]]
        mock_qr.metadatas = [[{"owner": "ABM"}]]
        mock_qr.distances = [[0.1]]
        self.registry.controller.query_collection.return_value = mock_qr
        
        phrasings = [
            "who are you?",
            "who developed you",
            "who made abm",
            "who built you?",
            "are you abm",
            "so you're not abm",
            "what is abm",
            "where did you come from",
            "who created you",
            "who programmed you"
        ]

        for phrase in phrasings:
            self.registry.gateway.generate.reset_mock()
            result = answerQuestion(phrase, registry=self.registry)
            
            self.assertIsInstance(result, AnswerResult)
            self.assertIn("Arabang's own initials", result.synthesis)
            self.assertNotIn("developed by Microsoft", result.synthesis)
            
            # Ensure the gateway.generate was NOT called (meaning the extractive path was used)
            self.registry.gateway.generate.assert_not_called()

    def test_project_isolation_guardrail(self):
        mock_router_result = MagicMock()
        from abm.orchestrator.departments import Department
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        self.registry.router.classify.return_value = mock_router_result

        self.registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        # Mock hits containing both a governance document and a client document
        mock_qr.ids = [["gate_cog_001", "external_doc_123"]]
        mock_qr.documents = [["ABM_SPEC.md: Local first by default.", "CleanNova Client Requirements: Must be fast."]]
        mock_qr.metadatas = [[{"owner": "ABM"}, {"source": "CleanNova"}]]
        mock_qr.distances = [[0.1, 0.2]]
        self.registry.controller.query_collection.return_value = mock_qr

        mock_response = MagicMock()
        mock_response.text = "Answer."
        self.registry.gateway.generate.return_value = mock_response

        answerQuestion("how should CleanNova be architected?", registry=self.registry)
        
        self.registry.gateway.generate.assert_called_once()
        prompt_used = self.registry.gateway.generate.call_args[0][0]
        
        # Verify the isolation rule was appended
        self.assertIn("PROJECT ISOLATION RULE", prompt_used)
        self.assertIn("NEVER propose editing, updating, or referencing ABM's own governance documents", prompt_used)
        self.assertIn("flowing paragraphs", prompt_used)

if __name__ == "__main__":
    unittest.main()
