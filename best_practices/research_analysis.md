# Research & Analysis Tasks Requiring Multi-Aspect Analysis

These tasks require in-depth analysis of multiple aspects of a topic to provide comprehensive answers.

Goal Examples:
- What makes TiDB a good choice for SaaS, especially for multi-tenancy architecture? (English)
- Can you provide an overview of TiDB, including its technical aspects, a gaming company use case, and pricing information? (English)
- Can you provide an overview of TiDB, including its technical aspects, a use case from a gaming company found in our blogs, and information on pricing? (English)
- What is the scalability of TiDB? (English)
- What is TiDB, and what are its main features and use cases? (English)
- Can you provide an overview of TiDB, including its technical aspects, a use case in a Web3 company using TiDB (specifically Chainbase and KNN3), and a comparison with MySQL? (English)
- What is TiCDC? (English)

---

# Standard Operating Procedure (SOP) for Research & Analysis Tasks Requiring Multi-Aspect Analysis

To effectively address complex questions that require in-depth analysis of multiple aspects of a topic, follow this structured approach:

---

## 1. Reasoning

- **Purpose**: Outline a clear and structured plan to address the multi-faceted question.
- **Action**: Use a `reasoning` instruction with `seq_no` 0.
- **Details**:
  - Provide a **chain of thoughts** that explains how you will tackle each aspect of the question.
  - Include a **dependency analysis** to show the relationships between steps and how they build upon each other.

## 2. Identify Key Aspects

- **Purpose**: Break down the main question into individual components or aspects that need to be addressed.
- **Action**: Use an `assign` instruction to list these aspects.
- **Details**:
  - Create a variable (e.g., `aspects_to_analyze`) that contains a list of the key aspects.
  - Ensure each aspect is clearly defined and relevant to the main question.

## 3. For Each Aspect

Repeat the following steps for each identified aspect to gather comprehensive information:

### a. Retrieve Knowledge Graph Data

- **Purpose**: Gather structured and authoritative information related to the specific aspect.
- **Action**: Use the `retrieve_knowledge_graph` tool in a `calling` instruction.
- **Details**:
  - Formulate a query that precisely targets the aspect.
  - Store the results in a variable with a descriptive name (e.g., `aspect_name_knowledge_graph`).

### b. Vector Search

- **Purpose**: Obtain detailed information from unstructured data sources to complement the knowledge graph data.
- **Action**: Use the `vector_search` tool in a `calling` instruction.
- **Details**:
  - Use specific queries to fetch relevant documents or examples related to the aspect.
  - Limit vector searches to batches of three to manage token limits.
  - Store results in variables with clear names (e.g., `aspect_name_vector_search_results`).

### c. LLM Generate Aspect Summary

- **Purpose**: Synthesize the gathered information into a coherent summary for the aspect.
- **Action**: Use the `llm_generate` tool in a `calling` instruction.
- **Details**:
  - Combine information from the knowledge graph and vector search results.
  - Provide a prompt that instructs the LLM to generate the summary in the required language.
  - Include necessary citations from the source URI.
  - Store the generated summary in a variable (e.g., `aspect_name_summary`).

## 4. Combine Aspect Summaries

- **Purpose**: Integrate individual aspect summaries into a comprehensive answer.
- **Action**: Use the `llm_generate` tool in a `calling` instruction.
- **Details**:
  - Collect all aspect summaries and include them in the context.
  - Provide a prompt that instructs the LLM to synthesize the summaries into a cohesive response.
  - Ensure the final summary flows logically and covers all aspects thoroughly.
  - Store the synthesized answer in a variable (e.g., `combined_summary`).

## 5. Assign Final Answer

- **Purpose**: Finalize the answer to be returned.
- **Action**: Use an `assign` instruction to set the `final_answer` variable.
- **Details**:
  - Ensure the `final_answer` is in the same language as specified in the goal.
  - Verify that all required information is included and that the answer is well-structured.
  - Incorporate any necessary formatting or additional information as per the goal's requirements.

---

**Requirements and Best Practices:**

- **Sequence Numbering**:
  - Use unique and sequential `seq_no` values starting from 0.
  - Ensure that the sequence logically flows and that each step builds upon the previous ones.

- **Variable Naming**:
  - Use descriptive and consistent names for variables to enhance readability (e.g., `scalability_features`, `performance_summary`).
  - Match variable names with their content for clarity.

- **Language Consistency**:
  - Ensure all instructions contributing to the `final_answer` are in the goal's language.
  - When inserting variables into the `final_answer`, verify they match the target language or have been processed to do so.

- **Instruction Types**:
  - Available types: `assign`, `reasoning`, `jmp`, `calling`.
  - The first instruction must be of type `reasoning`.

- **Final Answer Variable**:
  - The last instruction must assign the output to `final_answer`.
  - Use the variable `final_answer` consistently as the output variable throughout the plan.

- **Control Flow**:
  - Use `jmp` instructions if conditional logic or loops are necessary.
  - Manage execution flow effectively to handle dependencies between steps.

- **Token Management**:
  - When performing multiple `vector_search` operations, limit them to batches of three to prevent exceeding the LLM's token window limit.
  - After every three `vector_search` calls, use the `llm_generate` tool to summarize the aggregated results.

- **Citations**:
  - Include necessary citations from the source URI in the summaries and the final answer.
  - Ensure that citations are appropriately referenced and formatted.

---

**Example Plan Structure:**

- **Seq 0 (Reasoning)**:
  - **Type**: `reasoning`
  - **Parameters**:
    - `chain_of_thoughts`: Outline the structured approach to answer the question.
    - `dependency_analysis`: Explain dependencies between steps.

- **Seq 1 (Identify Aspects)**:
  - **Type**: `assign`
  - **Parameters**:
    - `aspects_to_analyze`: List of aspects to be addressed.

- **Seq 2-n (For Each Aspect)**:
  - **Type**: `calling`
  - **Tools**:
    - `retrieve_knowledge_graph` for aspect data.
    - `vector_search` for additional information.
    - `llm_generate` for aspect summary.
  - **Parameters**:
    - **For `retrieve_knowledge_graph`**:
      - `query`: Specific to the aspect.
      - `output_vars`: Store results in a variable.
    - **For `vector_search`**:
      - `query`: Targeted to fetch additional details.
      - `top_k`: Number of results to retrieve.
      - `output_vars`: Store results in a variable.
    - **For `llm_generate`**:
      - `context`: Include data from previous steps.
      - `prompt`: Instruct the LLM to generate the summary.

- **Seq n+1 (Combine Aspect Summaries)**:
  - **Type**: `calling`
  - **Tool**: `llm_generate`
  - **Parameters**:
    - `context`: Include all aspect summaries.
    - `prompt`: Instruct the LLM to synthesize the summaries.

- **Seq n+2 (Assign Final Answer)**:
  - **Type**: `assign`
  - **Parameters**:
    - `final_answer`: Assign the synthesized answer.
