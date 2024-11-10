# QA Tasks Requiring Manual Reference & Documentation Summary

These are straightforward questions that can be directly answered by referring to official documentation.

Goal Examples:
- Does TiDB support vector search? (English)
- Who uses TiDB? (English)
- How is vector search used? (Chinese)
- What’s new in TiDB version 8.1.0? (Chinese)
- What’s the latest version of TiDB? (Chinese)
- Does TiDB support smooth upgrades? Please provide details. (Chinese)
- How can I determine the version of TiDB that I am using? (English)
- What is the data format when Drainer delivers to Kafka? (Chinese)
- What’s the latest non-stable version of TiDB? (Chinese)
- Does TiDB support FOREIGN KEY constraints? (English)
- Could you provide a detailed explanation of what “tiem” refers to? (English)
- How do you define a unique index for a field? (Chinese)
- How is vector search implemented in TiDB? (English)

---

# Standard Operating Procedure (SOP) for QA Tasks Requiring Manual Reference & Documentation Summary

To efficiently address straightforward questions that can be directly answered by referring to official documentation, follow this structured approach:

---

## 1. Reasoning

- **Purpose**: Begin by outlining a clear plan to address the question.
- **Action**: Use a `reasoning` instruction with `seq_no` 0 to describe the steps you will take.
- **Details**:
  - Provide a **chain of thoughts** explaining how you will use available tools.
  - Include a **dependency analysis** to show the relationship between steps.

## 2. Retrieve Knowledge Graph

- **Purpose**: Gather structured and authoritative information related to the question.
- **Action**: Use the `retrieve_knowledge_graph` tool in a `calling` instruction.
- **Details**:
  - Formulate a query that precisely targets the needed information.
  - Store the results in a descriptively named variable (e.g., `knowledge_graph_data`).

## 3. Vector Search (if necessary)

- **Purpose**: Obtain additional detailed information from unstructured data sources.
- **Action**: Use the `vector_search` tool in a `calling` instruction.
- **Details**:
  - Use specific queries to fetch relevant documents or examples.
  - Limit vector searches to batches of three to manage token limits.
  - Store results in variables with clear names (e.g., `vector_search_results`).

## 4. LLM Generate

- **Purpose**: Synthesize the gathered information into a coherent and comprehensive answer.
- **Action**: Use the `llm_generate` tool in a `calling` instruction.
- **Details**:
  - Combine information from the knowledge graph and vector search results.
  - Provide a prompt that instructs the LLM to generate the answer in the required language.
  - Include necessary citations from the `source_uri`.
  - Store the generated text in a variable (e.g., `synthesized_answer`).

## 5. Assign Final Answer

- **Purpose**: Finalize the answer to be returned.
- **Action**: Use an `assign` instruction to set the `final_answer` variable.
- **Details**:
  - Ensure the `final_answer` is in the same language as specified in the goal.
  - Incorporate any required formatting or additional information.


---

**Requirements and Best Practices:**

- **Sequence Numbering**: Use unique and sequential `seq_no` values starting from 0.
- **Variable Naming**: Choose descriptive names for variables to enhance readability.
- **Language Consistency**:
  - Ensure all instructions contributing to the `final_answer` are in the goal’s language.
  - When inserting variables into the `final_answer`, verify they match the target language.
- **Instruction Types**:
  - Available types: `assign`, `reasoning`, `jmp`, `calling`.
  - The first instruction must be of type `reasoning`.
- **Final Answer Variable**:
  - The last instruction must assign the output to `final_answer`.
  - The variable `final_answer` should be used consistently as the output variable.

---

**Example Plan Structure:**

- **Seq 0 (Reasoning)**:
  - **Type**: `reasoning`
  - **Parameters**:
    - `chain_of_thoughts`: Describe the approach to answer the question.
    - `dependency_analysis`: Explain dependencies between steps.

- **Seq 1 (Retrieve Knowledge Graph)**:
  - **Type**: `calling`
  - **Tool**: `retrieve_knowledge_graph`
  - **Parameters**:
    - `query`: Specific to the question.
    - `output_vars`: Store results in a variable.

- **Seq 2 (Vector Search) (if necessary)**:
  - **Type**: `calling`
  - **Tool**: `vector_search`
  - **Parameters**:
    - `query`: Targeted to fetch additional details.
    - `top_k`: Number of results to retrieve.
    - `output_vars`: Store results in a variable.

- **Seq 3 (LLM Generate)**:
  - **Type**: `calling`
  - **Tool**: `llm_generate`
  - **Parameters**:
    - `context`: Include data from previous steps.
    - `prompt`: Instruct the LLM to generate the answer, specifying language and citation requirements.
    - `output_vars`: Store the generated answer.

- **Seq 4 (Assign Final Answer)**:
  - **Type**: `assign`
  - **Parameters**:
    - `final_answer`: Assign the generated answer to this variable.
