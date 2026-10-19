import json
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from src.db import DEFAULT_CRITERIA
from src.evaluator import EvaluatorError, evaluate_proposal
from src.llm_schemas import ScorecardReview, TenderScorecard


def criteria():
    return [
        {
            "criterion_id": row[0],
            "name": row[1],
            "description": row[2],
            "weight": row[3],
            "max_score": row[4],
        }
        for row in DEFAULT_CRITERIA
    ]


def scorecard(*, missing_criterion: bool = False, evidence_page: int = 1):
    active = criteria()
    if missing_criterion:
        active = active[:-1]
    return {
        "supplier_name": "Model-provided name is ignored",
        "criteria": [
            {
                "criterion_id": row["criterion_id"],
                "score": 7,
                "max_score": row["max_score"],
                "justification": "The proposal supports this assessment.",
                "evidence": f"Page 1 evidence for {row['criterion_id']}.",
                "evidence_page": evidence_page,
                "confidence": "medium",
                "missing_evidence": [],
            }
            for row in active
        ],
        "risks": [],
        "overall_summary": "Evidence-grounded model summary.",
    }


def review(*, unsupported: bool = False):
    return {
        "passed": not unsupported,
        "findings": (
            [
                {
                    "criterion_id": "quality_system",
                    "severity": "high",
                    "explanation": "The stated score exceeds the cited evidence.",
                }
            ]
            if unsupported
            else []
        ),
        "risks": [],
    }


class FakeStructuredLlm:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.configs = []

    def invoke(self, messages, *, config):
        self.configs.append((messages, config))
        output = self.outputs.pop(0)
        if isinstance(output, dict) and output.get("_raw_json_response"):
            return {
                "parsed": None,
                "raw": AIMessage(content=output["content"]),
                "parsing_error": output.get("parsing_error", "provider wrapper mismatch"),
            }
        return {
            "parsed": output,
            "raw": AIMessage(content="structured response"),
            "parsing_error": None,
        }


class FakeChatOpenAI:
    def __init__(self, scorecards, reviews):
        self.models = {
            TenderScorecard: FakeStructuredLlm(scorecards),
            ScorecardReview: FakeStructuredLlm(reviews),
        }

    def with_structured_output(self, schema, *, include_raw, method=None):
        if method is not None:
            assert method == "json_mode"
        assert include_raw is True
        return self.models[schema]


def call_evaluator(*, page_count: int | None = None, provider: str = "OpenAI"):
    with patch("src.evaluator.Client") as langsmith_client, patch(
        "src.evaluator.tracing_context"
    ) as trace_context:
        result = evaluate_proposal(
            "Supplier",
            "[Page 1]\nProposal facts",
            criteria(),
            provider=provider,
            api_key="test-provider-key",
            model="gpt-4o-mini",
            langsmith_api_key="test-langsmith-key",
            langsmith_project="test-project",
            run_id="test-run",
            page_count=page_count,
        )
    langsmith_client.assert_called_once_with(api_key="test-langsmith-key")
    langsmith_client.return_value.close.assert_called_once_with()
    assert trace_context.call_args.kwargs == {
        "enabled": True,
        "client": langsmith_client.return_value,
        "project_name": "test-project",
    }
    return result


def test_valid_scorecard_gets_deterministic_and_llm_validation():
    fake_chat = FakeChatOpenAI([scorecard()], [review()])
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat) as chat_openai:
        result, raw = call_evaluator()

    assert len(result["criteria"]) == len(criteria())
    assert result["supplier_name"] == "Supplier"
    assert result["criteria_by_id"]["quality_system"]["score"] == 7
    assert result["llm_validation"] == {
        "passed": True,
        "findings": [],
        "risks": [],
    }
    assert raw == "structured response"
    assert chat_openai.call_args.kwargs["model"] == "gpt-4o-mini"
    assert "base_url" not in chat_openai.call_args.kwargs
    assert fake_chat.models[TenderScorecard].configs[0][1]["tags"] == [
        "tender-evaluation",
        "scorecard-generation",
    ]
    assert fake_chat.models[TenderScorecard].configs[0][1]["metadata"]["evaluation_run_id"] == "test-run"
    assert fake_chat.models[ScorecardReview].configs[0][1]["tags"] == [
        "tender-evaluation",
        "llm-evidence-validation",
    ]
    critic_messages = fake_chat.models[ScorecardReview].configs[0][0]
    assert any(
        "JSON" in message.content
        for message in critic_messages
        if isinstance(message.content, str)
    )


def test_raw_json_scorecard_is_used_when_provider_schema_parser_fails():
    raw_scorecard = json.dumps(scorecard())
    wrapped_response = {
        "_raw_json_response": True,
        "parsing_error": "provider returned a valid JSON object with a schema mismatch",
        "content": f"```json\n{raw_scorecard}\n```",
    }
    fake_chat = FakeChatOpenAI([wrapped_response], [review()])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, raw = call_evaluator()

    assert result["criteria_by_id"]["quality_system"]["score"] == 7
    assert raw.startswith("```json")
    assert len(fake_chat.models[TenderScorecard].configs) == 1


def test_graph_repairs_incomplete_scorecard_once():
    fake_chat = FakeChatOpenAI(
        [scorecard(missing_criterion=True), scorecard()],
        [review()],
    )
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert len(fake_chat.models[ScorecardReview].configs) == 1
    assert len(result["criteria"]) == len(criteria())
    assert "exactly one result for each active criterion" in generation_calls[1][0][-1].content


def test_graph_repairs_evidence_page_outside_document_bounds():
    fake_chat = FakeChatOpenAI(
        [scorecard(evidence_page=4), scorecard()],
        [review()],
    )
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator(page_count=3)

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert "Evidence page exceeds the 3-page proposal" in generation_calls[1][0][-1].content
    assert result["criteria_by_id"]["quality_system"]["evidence_page"] == 1


def test_llm_evidence_critic_finding_routes_through_single_repair():
    fake_chat = FakeChatOpenAI(
        [scorecard(), scorecard()],
        [review(unsupported=True), review()],
    )
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert "exceeds the cited evidence" in generation_calls[1][0][-1].content
    assert result["llm_validation"]["passed"] is True


def test_wrapped_openrouter_critic_json_is_normalized_from_raw_response():
    wrapped_response = {
        "_raw_json_response": True,
        "parsing_error": "Failed to parse ScorecardReview from completion",
        "content": (
            '{"validation_result":{"supplier_name":"Supplier","findings":[],'
            '"risks":["All supplier claims require independent verification."],'
            '"overall_validation":"pass"}}'
        ),
    }
    fake_chat = FakeChatOpenAI([scorecard()], [wrapped_response])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert result["llm_validation"] == {
        "passed": True,
        "findings": [],
        "risks": ["All supplier claims require independent verification."],
    }
    assert "All supplier claims require independent verification." in result["risks"]
    assert len(fake_chat.models[TenderScorecard].configs) == 1
    assert len(fake_chat.models[ScorecardReview].configs) == 1


def test_wrapped_provider_findings_map_issue_and_material_issue_fields():
    wrapped_response = {
        "_raw_json_response": True,
        "content": (
            '{"validation_result":{"supplier_name":"Synthetic Supplier",'
            '"findings":[{"criterion_id":"quality_system",'
            '"issue":"The source does not support this score.",'
            '"material_issue":true}],"risks":["Verify authenticity."],'
            '"overall_validation":"FAIL"}}'
        ),
    }
    fake_chat = FakeChatOpenAI(
        [scorecard(), scorecard()],
        [wrapped_response, review()],
    )

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert len(fake_chat.models[TenderScorecard].configs) == 2
    retry_request = fake_chat.models[TenderScorecard].configs[1][0][-1].content
    assert "quality_system (high): The source does not support this score." in retry_request
    assert result["llm_validation"]["passed"] is True
    assert "Verify authenticity." in result["risks"]


def test_wrapped_provider_finding_field_is_normalized():
    message = "The justification is supported by the proposal's stated evidence gap."
    wrapped_response = {
        "validation_result": {
            "passed": False,
            "findings": [
                {
                    "criterion_id": "manufacturing_capability",
                    "finding": message,
                }
            ],
        }
    }
    fake_chat = FakeChatOpenAI([scorecard()], [wrapped_response])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert len(fake_chat.models[TenderScorecard].configs) == 1
    assert result["llm_validation"] == {
        "passed": True,
        "findings": [
            {
                "criterion_id": "manufacturing_capability",
                "severity": "low",
                "explanation": message,
            }
        ],
        "risks": [],
    }


def test_wrapped_provider_text_findings_trigger_repair_with_context():
    finding = "The evidence does not establish quality and reliability."
    wrapped_response = {
        "_raw_json_response": True,
        "content": (
            '{"validation_result":{"passed":false,"findings":['
            f"{json.dumps(finding)}"
            '],"risks":[]}}'
        ),
    }
    fake_chat = FakeChatOpenAI(
        [scorecard(), scorecard()],
        [wrapped_response, review()],
    )

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert finding in generation_calls[1][0][-1].content
    assert result["llm_validation"]["passed"] is True


def test_raw_review_json_content_blocks_are_normalized():
    wrapped_response = {
        "_raw_json_response": True,
        "parsing_error": "provider-specific structured output parsing failed",
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "validation_result": "passed",
                        "findings": [],
                        "risks": ["Supplier claims require verification."],
                    }
                ),
            }
        ],
    }
    fake_chat = FakeChatOpenAI([scorecard()], [wrapped_response])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert result["llm_validation"] == {
        "passed": True,
        "findings": [],
        "risks": ["Supplier claims require verification."],
    }


def test_parsed_wrapped_provider_review_is_normalized_before_validation():
    finding = "The evidence does not establish quality and reliability."
    wrapped_response = {
        "validation_result": {
            "passed": False,
            "findings": [finding],
        }
    }
    fake_chat = FakeChatOpenAI(
        [scorecard(), scorecard()],
        [wrapped_response, review()],
    )

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert finding in generation_calls[1][0][-1].content
    assert result["llm_validation"]["passed"] is True


def test_provider_review_string_validation_result_is_normalized():
    wrapped_response = {
        "validation_result": "passed",
        "findings": [],
    }
    fake_chat = FakeChatOpenAI([scorecard()], [wrapped_response])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert result["llm_validation"] == {
        "passed": True,
        "findings": [],
        "risks": [],
    }
    assert len(fake_chat.models[TenderScorecard].configs) == 1
    assert len(fake_chat.models[ScorecardReview].configs) == 1


def test_provider_review_string_validation_failure_triggers_repair():
    finding = "The evidence does not establish quality standards."
    wrapped_response = {
        "validation_result": "failed",
        "findings": [finding],
    }
    fake_chat = FakeChatOpenAI(
        [scorecard(), scorecard()],
        [wrapped_response, review()],
    )

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    generation_calls = fake_chat.models[TenderScorecard].configs
    assert len(generation_calls) == 2
    assert finding in generation_calls[1][0][-1].content
    assert result["llm_validation"]["passed"] is True


def test_wrapped_review_with_only_low_findings_is_advisory():
    low_findings = [
        {
            "criterion_id": row["criterion_id"],
            "severity": "low",
            "explanation": (
                "The proposal acknowledges that further details are needed, "
                "so the limited justification is supported."
            ),
        }
        for row in criteria()
    ]
    wrapped_response = {
        "validation_result": {
            "passed": False,
            "findings": low_findings,
        }
    }
    fake_chat = FakeChatOpenAI([scorecard()], [wrapped_response])

    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        result, _ = call_evaluator()

    assert len(fake_chat.models[TenderScorecard].configs) == 1
    assert len(fake_chat.models[ScorecardReview].configs) == 1
    assert result["llm_validation"]["passed"] is True
    assert result["llm_validation"]["findings"] == low_findings


def test_graph_fails_closed_after_one_unsuccessful_repair():
    fake_chat = FakeChatOpenAI(
        [scorecard(missing_criterion=True), scorecard(missing_criterion=True)],
        [],
    )
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat):
        with pytest.raises(EvaluatorError, match="after one repair attempt"):
            call_evaluator()

    assert len(fake_chat.models[TenderScorecard].configs) == 2
    assert not fake_chat.models[ScorecardReview].configs


def test_empty_provider_key_is_rejected_before_client_construction():
    with patch("src.evaluator.ChatOpenAI") as chat_openai:
        with pytest.raises(EvaluatorError, match="OpenAI API key"):
            evaluate_proposal(
                "Supplier",
                "Proposal",
                criteria(),
                provider="OpenAI",
                api_key="",
                model="gpt-4o-mini",
                langsmith_api_key="test-langsmith-key",
                langsmith_project="test-project",
            )
    chat_openai.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "chat_class"),
    [
        ("Google Gemini", "ChatGoogleGenerativeAI"),
        ("Anthropic", "ChatAnthropic"),
    ],
)
def test_non_openai_provider_uses_its_langchain_adapter(provider, chat_class):
    fake_chat = FakeChatOpenAI([scorecard()], [review()])
    with patch(f"src.evaluator.{chat_class}", return_value=fake_chat) as constructor:
        with patch("src.evaluator.Client") as langsmith_client, patch(
            "src.evaluator.tracing_context"
        ):
            result, _ = evaluate_proposal(
                "Supplier",
                "[Page 1]\nProposal facts",
                criteria(),
                provider=provider,
                api_key="test-provider-key",
                model="provider-chat-model",
            )

    assert result["supplier_name"] == "Supplier"
    assert constructor.call_args.kwargs["model"] == "provider-chat-model"
    api_key = constructor.call_args.kwargs.get("api_key")
    assert api_key is not None
    if hasattr(api_key, "get_secret_value"):
        api_key = api_key.get_secret_value()
    assert api_key == "test-provider-key"
    langsmith_client.assert_not_called()


def test_langsmith_tracing_is_skipped_when_no_key_is_supplied():
    fake_chat = FakeChatOpenAI([scorecard()], [review()])
    with patch("src.evaluator.ChatOpenAI", return_value=fake_chat), patch(
        "src.evaluator.Client"
    ) as langsmith_client, patch("src.evaluator.tracing_context") as trace_context:
        result, _ = evaluate_proposal(
            "Supplier",
            "[Page 1]\nProposal facts",
            criteria(),
            provider="OpenAI",
            api_key="test-provider-key",
            model="gpt-4o-mini",
        )

    assert result["supplier_name"] == "Supplier"
    langsmith_client.assert_not_called()
    trace_context.assert_not_called()
