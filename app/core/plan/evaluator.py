import logging
import json
from typing import Dict, List, Optional

from app.llm.interface import LLMInterface
from app.utils import extract_json

logger = logging.getLogger(__name__)


def evaulate_answer(llm_client: LLMInterface, goal: str, final_answer: str, plan: str):
    evaluation_prompt = f"""You are tasked with evaluating and improving the effectiveness of a problem-solving workflow. Below is a description of a Goal, a Plan used to address it, and the Final Answer generated. Your task is to evaluate the quality of the answer and diagnose whether the Plan sufficiently aligns with the Goal.

------------------------------------
REVISED EVALUATION FRAMEWORK:

I. ANSWER QUALITY ASSESSMENT (Primary Focus)
1. Goal Resolution:
   - Does the Final Answer directly and completely address the user's Goal?
   - Are there any unresolved aspects of the Goal in the Final Answer?
   - For non-TiDB-related goals: Does the answer politely decline while maintaining professionalism?

2. Answer Relevance:
   - Does the answer contain irrelevant information that doesn't directly contribute to solving the Goal?
   - Are all technical references (e.g., TiDB documentation) directly applicable to the problem?

3. Actionability:
   - If needed, does the answer provide clear, executable steps or concrete solutions?
   - For complex problems: Does the answer demonstrate proper prioritization of issues?

II. PLAN VALIDATION (Secondary Check)
1. Logical Foundation:
   - Does the Plan structure logically lead to the Final Answer?
   - Are there missing steps that could improve answer quality?

2. Risk Detection:
   - Does the Plan contain steps that could lead to:
     * Irrelevant information inclusion
     * Technical inaccuracies
     * Overlooking critical aspects of the Goal
     * Raw data not processed by LLM generation tool

3. Efficiency Check:
   - Are there redundant steps that don't contribute to the Final Answer?
   - Could the Plan be simplified while maintaining answer quality?

4. Retrieval Best Practices Check:
   - Does the Plan implement dual retrieval (use both retrieve_knowledge_graph and vector_search tools) for each query?
   - After each dual retrieval, does the Plan immediately process combined results through LLM generation tool to:
     * Extract key insights specific to the query
     * Present a coherent, summarized narrative
   - Does the Plan avoid passing raw retrieved data to non-LLM tools?

III. INTEGRATION CHECK
- If the Answer is good but the Plan has issues: Can we accept the answer while flagging Plan improvements?
- If the Answer is bad but the Plan seems good: Require deeper analysis of execution

------------------------------------
DECISION LOGIC:
1. First evaluate Answer Quality:
   - If Answer fully resolves Goal → Accept (even with Plan imperfections)
   - If Answer partially resolves → Reject and request improvements
   - If Answer is irrelevant → Reject regardless of Plan quality

2. Then validate Plan:
   - For accepted Answers: Note Plan improvements for future optimizations
   - For rejected Answers: Specify whether issues stem from Plan flaws or execution errors

------------------------------------
YOUR OUTPUT FORMAT:
You must return a JSON object with the following keys:
1. "accept": Boolean value (true or false) indicating whether the Final Answer effectively resolves the Goal.
2. "plan_adjustment_suggestion": Provide a comprehensive analysis of how the Plan could be improved to fully address the user's goal.
3. "goal_classification": (Optional) A categorization of the goal type based on the guidelines (e.g., "Direct Problem Resolution", "Execution Error").

------------------------------------
EXAMPLE OUTPUT:
{{
  "accept": true,
  "plan_adjustment_suggestion": "While the answer is acceptable, the Plan could be improved by...",
  "goal_classification": "Direct Problem Resolution"
}}

Below are the inputs for your evaluation:

## Goal
{goal}

## Final Answer
{final_answer}

## Plan
{plan}

Now Let's think step by step! Do you best on this evaluation task!
"""

    try:
        response = llm_client.generate(evaluation_prompt)
        json_response = extract_json(response)
        return json.loads(json_response)
    except Exception as e:
        logger.error(f"Error evaluating task answer: {e}", exc_info=True)
        return None


def reflect_step_on_final_answer(
    llm_client: LLMInterface,
    goal: str,
    final_answer: str,
    current_step_no: int,
    plan: List[Dict],
    vm_state: Dict,
    feedback: Optional[str] = None,
) -> Dict:
    """Reflect on the current step and suggest optimizations for remaining steps.

    Args:
        goal: The original task goal
        final_answer: The final answer produced by the plan
        metadata: Additional task metadata

    Returns:
        {
            "should_optimize": bool,  # Whether optimization is possible
            "suggestion": str,     # Optimization suggestion explanation
        }
    """
    # Prepare the reflection prompt
    prompt = f"""
    Goal Input:
    {goal}

    Final Answer: {final_answer}

    Feedback: {feedback}
    
    Current Step ({current_step_no}):
    {json.dumps(plan[current_step_no], indent=2)}

    Current Execution State:
    {json.dumps(vm_state, indent=2)}

    Remaining Steps:
    {json.dumps(plan[current_step_no + 1:], indent=2)}

    Analyze final answer, and the feedback (if provided):
    1. Could the remaining steps be improved to generate a better final answer? Answer with true or false.
    2. If true, suggest specific improvements focusing on:
        - Adding new steps that could provide additional relevant information
        - Modifying existing steps to gather more comprehensive or accurate data
        - Enhancing the reasoning process using llm_generate to produce a more complete or accurate answer

    Note: Focus on improving answer quality rather than execution efficiency.

    Format your response as JSON:
    ```json
    {{
        "should_optimize": true/false,
        "suggestion": string,
    }}
    ```
    """

    try:
        # Get reflection from LLM
        response = llm_client.generate(prompt)
        response_json_str = extract_json(response)
        reflection = json.loads(response_json_str)

        return reflection
    except Exception as e:
        logger.error("Error during reflection: %s, %s", e, response, exc_info=True)
        return {
            "should_optimize": False,
            "suggestion": f"Error during reflection: {str(e)}, {response}",
        }


def evaluate_multiple_answers(
    llm_client: LLMInterface,
    goal: str,
    answers_list: List[Dict[str, str]],
) -> List[Dict]:
    """Evaluate and rank multiple answers based on their quality.

    Args:
        answers_list: List of answers with commit_hash and final_answer
        Example: [{"commit_hash": "abc123", "final_answer": "..."}, ...]

    Returns:
        Sorted list by score descending: [{"commit_hash": "abc123", "score": 9.5}, ...]
    """
    evaluation_prompt = f"""Evaluate and score multiple answers (0-10) based on their quality. 
Higher scores indicate better alignment with the goal. Consider:
1. Goal resolution completeness
2. Answer relevance and accuracy
3. Actionability of solutions
4. Technical correctness (for TiDB-related goals)

Goal Input:
{goal}

Answers to evaluate:
{json.dumps([{"commit_hash": a["commit_hash"], "answer": a["final_answer"]} 
            for a in answers_list], indent=2)}

Score each answer 0-10 following these rules:
- 9-10: Perfectly solves goal with optimal solution
- 7-8: Solves goal with minor improvements possible
- 5-6: Partially solves but misses key aspects
- 3-4: Contains major flaws
- 0-2: Completely irrelevant/invalid

Return JSON array with scores in this format:
[
  {{"commit_hash": "hash1", "score": score1}},
  {{"commit_hash": "hash2", "score": score2}}
]"""

    try:
        response = llm_client.generate(evaluation_prompt)
        scores = json.loads(extract_json(response))
        # Create mapping for quick lookup
        answer_map = {a["commit_hash"]: a["final_answer"] for a in answers_list}

        return sorted(
            [
                {
                    "commit_hash": s["commit_hash"],
                    "score": float(s["score"]),
                    "final_answer": answer_map.get(s["commit_hash"], "N/A"),
                }
                for s in scores
            ],
            key=lambda x: x["score"],
            reverse=True,
        )
    except Exception as e:
        logger.error(f"Error evaluating multiple answers: {e}", exc_info=True)
        return []
