# Specification for Generating Executable Plans for the Virtual Machine (VM)

## Table of Contents
1. Overview of the VM
2. Instruction Format
3. Supported Instructions
4. Parameters and Variable References
5. Variables and Dependencies
6. Plan Structure
7. Best Practices
8. Common Errors
9. Available Tools for calling instruction
10. Example Plan

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
    "random_number": 42,
    "final_answer": "{recommendations_report}"
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
    - compliance_check: A structured analysis of how the plan adheres to best practices and avoids common errors.
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
    "chain_of_thoughts": "To provide recommendations for the query, we'll follow this approach:\n\n1. Overall Strategy:\n   - Step 1: Gather initial information\n   - Step 2: Process and analyze data\n   - Step 3: Generate final recommendations\n\n2. Key Decision Points:\n   - Using multiple data sources for comprehensive coverage\n   - Implementing error handling for edge cases\n\n3. Limitations:\n   - Dependent on data freshness\n   - May require refinement based on specific use cases\n\n4. Compliance Checks:\n   - ✓ No user-specific queries planned (will not attempt to detect current version/configuration)\n   - ✓ All responses will maintain consistent language (English)\n   - ✓ Final recommendations will be stored in final_answer\n   - ✓ All variable references use correct ${var} syntax\n...",
    "dependency_analysis": "Step 2 depends on Step 1\nStep 2 depends on Step 2"
  }
}
```

## 4. Parameters and Variable References
Parameters can be either direct values or variable references. To reference a variable, use the format `${variable_name}`.

- **Direct Values** are used when you clearly know the corresponding parameter values. These values do not depend on the results of other instructions, ensuring clarity and simplicity. Using direct values helps improve query readability and maintainability, especially in scenarios where parameters do not need to change dynamically.

- **Variable References** are ideal for scenarios that require dynamic parameter value filling, enhancing the interconnectivity and data flow between instructions. By using variable references, parameters can be adjusted dynamically based on the results of previous steps, increasing the flexibility and automation of the workflow.

- **Don’t Use Math Expressions in Parameters and tool_params**: The VM does not have the capability to compute or parse expressions within parameters. It can only perform simple reference substitutions. For example, avoid using expressions like value1 + value2 or value * 2 within parameters, and instead, calculate these values explicitly in a prior step and refer to the result in the parameter.


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
      "top_k": 10
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

- **Avoid variable dependencies within a single "assign" instruction**：Since the order of variable assignments within an "assign" instruction is not defined, do not rely on one variable being assigned before another within the same instruction. Instead, split assignments across multiple instructions if one depends on another. For example, this is incorrect:

```json
{
  "seq_no": 3,
  "type": "assign",
  "parameters": {
    "y": "${x}",
    "x": 10
  }
}
```

"y" might end up being undefined because we cannot guarantee that "x" will be set first. The correct approach is to split them:

```json
{
  "seq_no": 3,
  "type": "assign",
  "parameters": {
    "x": 10
  }
},
{
  "seq_no": 4,
  "type": "assign",
  "parameters": {
    "y": "${x}"
  }
}
```

- **Best Practices for Utilizing Knowledge Graph Search**:
  - Retrieve Structured Data: Use the Knowledge Graph Search tool to obtain relevant structured knowledge data and their interrelationships.
  - Refine and Summarize: After retrieval, employ an LLM generation tool to refine and summarize the knowledge graph results. This ensures the information is precise, relevant, and tailored to the user’s query.

- **Best Practices for Utilizing Vector Search**:
  - Combine Multiple Searches: Enhance response depth and clarity by combining multiple Vector Search calls with different queries. Start by using Vector Search to gather extensive, context-rich document fragments related to the query.
  - Synthesize with LLM: Feed the gathered snippets into an LLM generation tool to synthesize and generate comprehensive answers.
  - Batch Processing: Limit multiple Vector Search operations to batches of three. After every three vector_search calls, use an LLM generation tool to summarize the aggregated results. This approach prevents exceeding the LLM’s token window limit and reduces the likelihood of token overflow errors.

- **Best Practices for Information Retrieval - Combining Knowledge Graph Search and Vector Search**:
  - Dual Retrieval: When retrieving information, utilize both Knowledge Graph Search and Vector Search simultaneously. This combination enhances the richness of the information by leveraging the structured data from the knowledge graph and the detailed insights from vector search.
  - Unified Summarization: After retrieving data from both tools, use an LLM generation tool to summarize the knowledge related to the query. Avoid directly using the loose data returned by the two tools; instead, ensure all retrieved information is processed through the LLM generation tool to create a coherent and well-structured final answer.
  - Tool Integration: Ensure that raw data retrieved from both Knowledge Graph Search and Vector Search is exclusively processed by the LLM generation tool. Do not pass this data to other tools, as doing so may result in an unreadable final answer or prevent other tools from effectively processing the data. This practice maintains the coherence, integrity, and quality of the final response.
  - Maintain Coherence: By processing all retrieved data through the LLM generation tool, you ensure that the final answer is a cohesive, single-language narrative. This avoids the inclusion of raw or fragmented data that could compromise the readability and consistency of the response.

## 8. Common Errors

**Case 1: Querying Specific Runtime/Environment Information**

**Error Example:**
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool_name": "tool_name",
    "tool_params": {
      "query": "Determin the current version of ..."
    },
    "output_vars": [...]
  }
}
```

```json
{
  "parameters": {
    "output_vars": [
      "slow_query_log_explanation",
      "sample_slow_query_log"
    ],
    "tool_name": "llm_generate",
    "tool_params": {
      "context": null,
      "prompt": "Please analyze the sql query: `SELECT * FROM INFORMATION_SCHEMA.SLOW_QUERY ORDER BY start_time DESC LIMIT 10;`. Explain the slow query and its relevant details(at least contain 'query', 'start_time', 'duration', 'plan_digest').\n\nPlease ensure that the generated text uses English."
    }
  },
  "seq_no": 2,
  "type": "calling"
}
```

**Error Explanation**:

- **Not allowed to execute SQL**：Please do not use any tools, such as llm_generate, to attempt to obtain SQL execution results.
- **Do Not Assume Specific Environment Information**: Do not make assumptions about (or generate) specific details of the environment, such as their current system configuration, current versions of tidb, current tiup version, or private data. Plans should be designed to be adaptable and not rely on presumed specific environment information.
- **Avoid Obtain Specific Data with General Tools**: General tools like `retrieve_knowledge_graph`, `vector_search` and `llm_generate` can only access public documentation and general knowledge. They cannot access:
  - Current system configuration
  - Current version
  - Cluster status
  - Any private or runtime information
  Such specific environment information can only be obtained through specialized tools explicitly designed for that purpose, or should be provided by the user as part of their query.

