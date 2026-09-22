from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ai.typesafe import SystemOneClient, TypeSafeError
from .models import MemoryDecision


@dataclass(frozen=True)
class MemoryJudgeResult:
    decision: MemoryDecision
    metadata: dict[str, Any]


class JevMemoryJudge:
    """Map Dianjia's memory policy to Jev questions and typed answers."""

    ACTIONS = {
        "create": "Create a new long-term memory because no existing memory covers this durable knowledge.",
        "update": "Append the candidate to one existing memory that covers the same subject.",
        "merge": "Use one primary memory and archive at least one other existing memory that duplicates the same knowledge.",
        "candidate": "Keep the candidate for human review because evidence or confidence is insufficient.",
        "discard": "Discard content that is temporary, non-reusable, or not useful as long-term memory.",
        "conflict": "Keep the candidate as a conflict because it contradicts established memory and needs review.",
    }

    def __init__(self, client: SystemOneClient | None = None):
        self.client = client or SystemOneClient()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    def decide(self, candidate: dict[str, Any], existing: list[dict[str, Any]]) -> MemoryJudgeResult:
        if not self.enabled:
            raise TypeSafeError("TYPESAFE_API_KEY is not configured")
        state = self._build_state(candidate, existing)
        questions = self._build_questions(existing)
        response = self.client.evaluate(state=state, questions=questions)
        answers = response["answers"]
        action, action_confidence, action_probabilities = self._choice_answer(answers, "action", set(self.ACTIONS))

        known_ids = [str(memory["id"]) for memory in existing]
        target: str | None = None
        target_confidence: float | None = None
        target_probabilities: dict[str, float] = {}
        merge_probabilities: dict[str, float] = {}
        if known_ids:
            selected, target_confidence, target_probabilities = self._choice_answer(answers, "target", {"none", *known_ids})
            target = None if selected == "none" else selected
            for index, memory_id in enumerate(known_ids):
                merge_probabilities[memory_id] = self._noul_answer(answers, f"merge_{index}")

        total_score = int(candidate.get("total_score", sum(candidate.get("score", {}).values())))
        final_action = action
        downgrade_reason = ""
        merge_ids: list[str] = []
        if action == "create" and total_score < 12:
            final_action = "candidate"
            downgrade_reason = f"候选总分 {total_score} 低于长期记忆阈值 12"
        elif action == "update" and target not in known_ids:
            final_action = "candidate"
            downgrade_reason = "Jev 未选择有效的更新目标"
        elif action == "merge":
            additional = [memory_id for memory_id, probability in merge_probabilities.items() if memory_id != target and probability >= 0.5]
            if target not in known_ids:
                final_action = "candidate"
                downgrade_reason = "Jev 未选择有效的合并主目标"
            elif not additional:
                final_action = "candidate"
                downgrade_reason = "Jev 未确认额外合并对象"
            else:
                merge_ids = [target, *additional]

        if final_action not in {"update", "merge"}:
            target = None
            merge_ids = []

        model = response["model"]
        reason = f"Jev {model} 选择 {action}（置信度 {action_confidence:.2f}）"
        if target:
            reason += f"，目标 {target}"
        if downgrade_reason:
            reason += f"；{downgrade_reason}，已转为待复核候选"
        decision = MemoryDecision(final_action, reason, target, action_confidence, total_score, {}, merge_ids)
        metadata = {
            "provider": "typesafe",
            "model": model,
            "selected_action": action,
            "action_confidence": action_confidence,
            "action_probabilities": action_probabilities,
            "target": target,
            "target_confidence": target_confidence,
            "target_probabilities": target_probabilities,
            "merge_probabilities": merge_probabilities,
            "usage": response.get("usage", {}),
        }
        return MemoryJudgeResult(decision, metadata)

    @classmethod
    def _build_state(cls, candidate: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any]:
        candidate_state = {
            key: candidate.get(key)
            for key in ("title", "category", "subcategory", "tags", "summary", "score", "total_score")
        }
        candidate_state["content"] = str(candidate.get("content") or "")[:8000]
        remaining = 12000
        existing_state = []
        for memory in existing[:5]:
            content = str(memory.get("content") or "")[:max(0, remaining)]
            remaining -= len(content)
            existing_state.append({
                "id": str(memory["id"]),
                "title": str(memory.get("title") or ""),
                "category": str(memory.get("category") or ""),
                "content": content,
            })
        return {
            "candidate": candidate_state,
            "existing_memories": existing_state,
            "policy": {
                "long_term_score_threshold": 12,
                "preserve_uncertain_or_conflicting_content_for_review": True,
                "only_select_memory_ids_present_in_existing_memories": True,
            },
        }

    @classmethod
    def _build_questions(cls, existing: list[dict[str, Any]]) -> dict[str, Any]:
        questions: dict[str, Any] = {
            "action": {
                "type": "choice",
                "instructions": "Choose the safest memory action for `candidate` using `existing_memories` and `policy`. Prefer review over an unsafe write.",
                "criteria": dict(cls.ACTIONS),
            }
        }
        if existing:
            target_criteria = {"none": "No existing memory is a valid primary target."}
            for memory in existing[:5]:
                memory_id = str(memory["id"])
                target_criteria[memory_id] = f"Use existing memory `{memory_id}` as the primary update or merge target."
            questions["target"] = {
                "type": "choice",
                "instructions": "Assuming `candidate` should update or merge with an existing memory, choose the single best primary target from `existing_memories`; otherwise choose `none`.",
                "criteria": target_criteria,
            }
            for index, memory in enumerate(existing[:5]):
                questions[f"merge_{index}"] = {
                    "type": "noul",
                    "instructions": f"Should `existing_memories[{index}]` be archived into the primary memory as part of a merge with `candidate`? Answer yes only for genuinely duplicative knowledge.",
                }
        return questions

    @staticmethod
    def _choice_answer(answers: dict[str, Any], question_id: str, allowed: set[str]) -> tuple[str, float, dict[str, float]]:
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise TypeSafeError(f"TypeSafe answer `{question_id}` is not a Choice")
        choice = str(answer.get("choice") or "")
        if choice not in allowed:
            raise TypeSafeError(f"TypeSafe answer `{question_id}` selected an unknown option")
        try:
            confidence = float(answer["confidence"])
            probabilities = {str(key): float(value) for key, value in answer["probabilities"].items()}
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise TypeSafeError(f"TypeSafe answer `{question_id}` has invalid probabilities") from exc
        if not 0 <= confidence <= 1 or any(not 0 <= value <= 1 for value in probabilities.values()):
            raise TypeSafeError(f"TypeSafe answer `{question_id}` contains values outside 0..1")
        if choice not in probabilities:
            raise TypeSafeError(f"TypeSafe answer `{question_id}` omitted the selected probability")
        return choice, confidence, probabilities

    @staticmethod
    def _noul_answer(answers: dict[str, Any], question_id: str) -> float:
        answer = answers.get(question_id)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise TypeSafeError(f"TypeSafe answer `{question_id}` is not a Noul")
        try:
            value = float(answer["noul"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TypeSafeError(f"TypeSafe answer `{question_id}` has an invalid Noul value") from exc
        if not 0 <= value <= 1:
            raise TypeSafeError(f"TypeSafe answer `{question_id}` contains a value outside 0..1")
        return value
