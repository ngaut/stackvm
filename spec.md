# Specification for Generating Executable Plans for the Virtual Machine (VM)

## Table of Contents
1. Overview of the VM
2. Instruction Format
3. Supported Instructions
4. Parameters and Variable References
5. Variables and Dependencies
6. Plan Structure
7. Best Practices
8. Available Tools for calling instruction
9. Example Plan

## 1. Overview of the VM
The VM executes plans consisting of a sequence of instructions. Each instruction performs a specific operation and may interact with variables stored in a variable store. The VM supports conditional execution and can handle dependencies between instructions through variable assignments and references.

### Key features:
- **Variable Store**: A key-value store where variables are stored and accessed by name.
- **Instruction Execution**: Instructions are executed sequentially unless control flow is altered by conditional statements.

## 2. Instruction Format
Each instruction in the plan is represented as a JSON object with the following keys:

- `seq_no`: A unique and AUTO-INCREMENT integer identifying the instruction's sequence within the plan, starting from 0.
- `type`: A string indicating the instruction type. See Supported Instructions.
- `parameters`: An object containing parameters required by the instruction.

```json
{
  "seq_no": N,
  "type": "instruction_type",
  "parameters": {
    "param1": "value_or_variable_reference",
    "param2": "value_or_variable_reference"
  }
}
```

## 3. Supported Instructions
### 3.1 assign
- **Purpose**: Assigns values to one or more variables.
- **Parameters**: An object where each key is a variable name and each value is either a direct value or a variable reference.

**Example:**
```json
{
  "seq_no": 1,
  "type": "assign",
  "parameters": {
    "number": 42,
    "explanation": "The choosen number is ${number}"
  }
}
```

### 3.2 jmp
- **Purpose**: Jumps to a specified sequence number based on an optional condition.
- **Parameters**:
  - `condition_prompt` (optional): The prompt to evaluate the condition. If provided, the LLM evaluates whether to jump. **Must respond with a JSON object in the following format:**
    ```json
    {
      "result": boolean,
      "explanation": string
    }
    ```
  - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.
  - `jump_if_true`: The `seq_no` to jump to if the condition evaluates to true. Required if `condition_prompt` is provided.
  - `jump_if_false` (optional): The `seq_no` to jump to if the condition evaluates to false. Required if `condition_prompt` is provided.
  - `target_seq` (optional): The `seq_no` to jump to if no condition is provided (unconditional jump).

**Example (Conditional Jump):**
```json
{
  "seq_no": 4,
  "type": "jmp",
  "parameters": {
    "condition_prompt": "Is ${number} even? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if the number is even, false otherwise, and 'explanation' provides a brief reason for the result.",
    "context": null,
    "jump_if_true": 5,
    "jump_if_false": 6
  }
}
```

**Example (Unconditional Jump):**
```json
{
  "seq_no": 5,
  "type": "jmp",
  "parameters": {
    "target_seq": 7
  }
}
```

### 3.3 calling
- **Purpose**: Invokes a specific tool or function with the provided parameters.
- **Parameters**: Defines the specifications required to call a tool.
  - `tool_name`: The name of the tool to be called for `calling` instruction.
  - `tool_params`: An object containing key-value pairs that represent the arguments required by the specified tool.
    - Keys: Must match the argument names expected by the tool.
    - Values: Can be either a direct value or a variable reference.
  - `output_vars` (optional): An array specifying how the tool's output should be stored in the VM's variable store for later use.
    - If it is a string: The array contains one variable name. The entire tool's response is stored under this variable name.
    - If it is an array: The array contains variable names corresponding to the keys in the JSON response. Each variable name in the array maps to a key in the JSON object, and the value associated with each key will be extracted and stored under the corresponding variable name.

**Example:**
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool_name": "tool_name",
    "tool_params": {
      "param1": "value_or_variable_reference",
      "param2": "value_or_variable_reference"
    },
    "output_vars": ["variable_name_1", ...]
  }
}
```

Below is an example where the calling type is configured to use the `llm_generate` tool. It specifies the tool name and its parameters, including a prompt to analyze sales data, a reference to the sales_data variable for context, and a JSON response format. The tool's output is stored in two variables: summary and insights. This setup allows the tool to process the sales data and save the results for later use.
**Example:**
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool_name": "llm_generate",
    "tool_params": {
      "prompt": "Analyze the sales data and provide summary and insights, response in json format including keys ['summary', 'insights']",
      "context": "${sales_data}",
    },
    "output_vars": ["summary", "insights"]
  }
}
```

### 3.4 reasoning
- **Purpose**: Provides a detailed explanation of the plan's reasoning process, analysis, and steps.
- **Parameters**:
  - `chain_of_thoughts`: A string containing a comprehensive breakdown of the reasoning process.
    - The overall strategy for approaching the problem
    - Key decision points and rationale for choices made
    - Assumptions and their justifications
    - Potential alternative approaches considered
    - Expected outcomes of each major step
    - How different pieces of information are intended to be combined
    - Any limitations or potential issues with the chosen approach
  - `dependency_analysis`: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

**Example:**
```json
{
  "seq_no": 0,
  "type": "reasoning",
  "parameters": {
    "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach:

    1. Overall Strategy:
       We'll follow these steps:
         1. Determine the latest stable version of TiDB
         2. Gather version-specific information
         3. Collect general TiDB information (if needed)
         4. Gather performance optimization techniques
         5. Collect e-commerce-specific optimizations
         6. Synthesize gathered information into actionable recommendations

    2. Key Decision Points and Rationale:
       a. Using both knowledge graph and vector search: This allows us to leverage structured relationships (knowledge graph) and semantic similarity (vector search) for comprehensive information gathering.
       b. Conditional logic for version determination: This helps us handle cases where the exact version might not be clear from the knowledge graph data.

    3. Assumptions:
       - The latest stable version of TiDB is the most relevant for current optimization practices.
       - E-commerce applications have specific performance requirements that may differ from general use cases.

    4. Alternative Approaches Considered:
       - We could have used only vector search, but this might miss important structured relationships in the data.
       - We could have skipped version-specific information, but this would likely result in less accurate and relevant recommendations.

    5. Expected Outcomes:
       - Step 1-2: Identification of the latest TiDB version
       - Step 3-6: Gathering of version-specific and general TiDB information
       - Step 7-8: Collection of performance techniques and e-commerce-specific optimizations
       - Step 9-10: Synthesis of gathered information into actionable recommendations

    6. Information Combination:
       The LLM will synthesize the version-specific features, general performance techniques, and e-commerce considerations to create a comprehensive set of recommendations.

    7. Limitations:
       - The accuracy of our recommendations depends on the freshness of the knowledge graph and vector database.
       - If no specific version is found, our recommendations may be more general and less tailored.

    This approach allows us to provide version-specific, relevant, and comprehensive optimization recommendations for TiDB in an e-commerce context.",
    "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2.\nStep 4 depends on Step 3 (if condition is true).\nStep 5 depends on Step 4 when condition is true (to skip Step 6).\nStep 6 depends on Step 3 (if condition is false).\nStep 7 depends on Step 4 or Step 6.\nStep 8 depends on Step 7.\nStep 9 depends on Step 8.\nStep 10 depends on Step 9."
  }
}
```

## 4. Parameters and Variable References
Parameters can be either direct values or variable references. To reference a variable, use the format `${variable_name}`.

- **Direct Values** are used when you clearly know the corresponding parameter values. These values do not depend on the results of other instructions, ensuring clarity and simplicity. Using direct values helps improve query readability and maintainability, especially in scenarios where parameters do not need to change dynamically.

- **Variable References** are ideal for scenarios that require dynamic parameter value filling, enhancing the interconnectivity and data flow between instructions. By using variable references, parameters can be adjusted dynamically based on the results of previous steps, increasing the flexibility and automation of the workflow.


**Direct Value Example:**
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool_name": "retrieve_knowledge_graph",
    "tool_params": {
      "query": "TiDB latest stable version"
    },
    "output_vars": ["latest_tidb_version_info"]
  }
}
```

**Variable Reference Example:**
```json
{
  "seq_no": 4,
  "type": "calling",
  "parameters": {
    "tool_name": "vector_search",
    "tool_params": {
      "query": "What are the key features and improvements in TiDB version ${latest_stable_tidb_version}?",
      "top_k": 3
    },
    "output_vars": ["tidb_key_features_and_improvements"]
  }
}
```

## 5. Variables and Dependencies
- **Variable Assignment**: Use the `assign` instruction or specify an `output_vars` in a `calling` instruction that produces outputs.
- **Variable Access**: Reference variables in parameters using the variable reference format.
- **Dependencies**: Manage dependencies by assigning outputs to variables and referencing them in subsequent instructions.

## 6. Plan Structure
- **Sequential Execution**: Instructions are executed in order based on their `seq_no`.
- **Control Flow**: Use the `jmp` instruction for branching logic and conditional loops.

## 7. Best Practices
- **Sequence Numbering**: Ensure that `seq_no` values are unique and sequential within the plan.
- **Variable Naming**: Use descriptive variable names to make the plan readable and maintainable.
- **Control Flow**: Use `jmp` instructions to create conditional logic, manage execution flow, and implement loops effectively.
- **Final answer**: The name of output var of The last instruction MUST be "final_answer".
- **Language Consistency**:
  - **Requirement**: All the instructions (e.g. `assign`) that directly contribute to generating the `final_answer` must be written in the same language as the goal. This ensures the final output is consistent with the intended language.

  - **For `assign` Instructions**:
    - **Language Consistency**: Ensure the content being assigned is in the same language as the goal.
    - **Variable Content**: When inserting variables into the `final_answer`, make sure they are in the target language or have been processed to match it.

- **Instruction type selection**: Available instruction types:[assign, reasoning, jmp, calling]. The type of first instruction is always "reasoning" and 'seq_no' starts from 0.
- **Best Practices for Utilizing Knowledge Graph Search**:
  1. When a knowledge graph is available, begin by using the Knowledge Graph Search tool to retrieve relevant knowledge points and understand the relationships between them.
  2. After retrieving knowledge, integrate the question with the knowledge graph data. Use an LLM generation tool to analyze both the user's intent and the graph data, generating a more precise knowledge for the question.
- **Best Practices for Utilizing Vector Search**:
  - To optimize its use, combine multiple Vector Search calls (with different queries) with an LLM generation tool to enhance the depth and clarity of the responses. Start by employing the Vector Search to gather extensive and context-rich document fragments related to the query. Then, feed these detailed snippets into the LLM generation tool to synthesize and generate comprehensive answers.
  - When performing multiple Vector Search operations, limit them to batches of three. After every three `vector_search` calls, use an LLM generation tool to summarize the aggregated results.  This approach helps prevent exceeding the LLM's token window limit, reducing the likelihood of errors related to token overflow.
