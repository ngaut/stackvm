import logging
import json

from app.llm.interface import LLMInterface
from app.utils import extract_json

logger = logging.getLogger(__name__)


def evaulate_answer(
    llm_client: LLMInterface, goal: str, metadata: dict, final_answer: str, plan: str
):
    evaluation_prompt = f"""You are tasked with evaluating and improving the effectiveness of a problem-solving workflow. Below is a description of a Goal, a Plan used to address it, and the Final Answer generated. Your task is to evaluate the quality of the answer and diagnose whether the Plan sufficiently aligns with the Goal.

------------------------------------
KEY POINTS TO CONSIDER IN YOUR EVALUATION:
1. Deep Analysis of the User's Problem:
  - Does the Plan demonstrate a sufficient understanding of the user's overall background, constraints, and specific questions?
  - Has the Plan identified the critical context that shapes the user's goal (e.g., large data volumes, performance constraints, GC usage, version details, etc.)?

2. Instructions Context & Coverage:
  - For each instruction in the Plan (including steps like searching for relevant data or generating partial solutions), verify whether it explicitly or implicitly incorporates the "specific problem background + user's question."
  - Do the instructions effectively handle the sub-questions or concerns raised by the user? Are any key points missing or glossed over?

3. Verification of Problem Decomposition and Factual Information Retrieval for TiDB-Related Goals
  - Problem Decomposition - If the Goal is TiDB-related, verify whether the Plan has effectively broken down the Goal into distinct sub-questions.
  - Individual Retrieval Methods for Each Sub-Question - For each sub-question, verify wheter the plan has applied the following retrieval methods independently:
    - retrieve_knowledge_graph + vector_search: to fetch background knowledge or technical details relevant to TiDB.
    - llm_generate: after obtaining the above retrieval information, use it as the basis for reasoning and extracting the most relevant information.
  - Ensuring Relevance and Separation:
    - Confirm that each sub-question is handled separately, ensuring that the retrieval process targets the most relevant data for that specific sub-question.
    - Ensure that retrieval operations for different sub-questions are not combined, preventing the mixing of data across sub-questions.

4. Completeness of the Plan:
   • Does the Plan address all major aspects of the user's problem or goal?
   • Are there any unanswered questions or issues that the user might still have after following the Plan?

5. Cohesion of Plan Steps:
   • Assess whether the Plan's instructions flow logically from one step to the next, and whether they form a coherent end-to-end workflow.
   • Consider whether the Plan's approach to searching for data, filtering out irrelevant information, and eventually generating a final integrated solution is clearly articulated and consistent with the user's context.

When providing your evaluation, reference these points and also consider the following general guidelines:

- Direct Problem Resolution: The Plan and Final Answer should yield a clear, actionable solution or next step.
- Clarification of User Intent: If the Goal is unclear or missing details, verify if the Plan seeks clarification properly, clarification is enough for this kind of goa, no other process is needed.
- Unrelated to TiDB: If the Goal is not TiDB-related, ensure the Plan provides a polite response indicating the capability to assist with TiDB-related queries only.
- Providing Relevant Information: Ensure the solution or Plan steps remain focused on the user's needs, without extraneous or off-topic content.
- Maintaining Conversational Flow: The explanation or solution should guide the user logically from their question to the solution, smoothly transitioning between steps.

------------------------------------
YOUR OUTPUT FORMAT:
You must return a JSON object with the following keys:
1. "accept": Boolean value (true or false) indicating whether the Final Answer effectively resolves the Goal.
2. "answer_quality_assessment_explanation": A detailed explanation justifying why the final answer does or does not meet the goal, referencing any guidelines or key points above.
3. "plan_adjustment_suggestion": If "accept" is false, provide a comprehensive analysis of how the Plan could be improved to fully address the user's context and questions. Propose modifications or additional steps in detail.
4. "goal_classification": (Optional) A categorization of the goal type based on the guidelines (e.g., "Direct Problem Resolution", "Clarification Needed").

------------------------------------
EXAMPLE OUTPUT:
{{
  "accept": false,
  "answer_quality_assessment_explanation": "...",
  "plan_adjustment_suggestion": "...",
  "goal_classification": "Direct Problem Resolution"
}}

Below are the inputs for your evaluation:

## Goal
{goal}

## Supplementary goal information
{metadata.get('response_format')}

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
        logger.error(f"Error evaluating task answer: {e}")
        return None
