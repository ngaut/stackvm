Your task is to generate a detailed action plan to achieve the following goal: does tidb support sql? {'lang': 'Japanese'}

**MUST follow the Specification**:
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
- **Parameters**: An object where each key is a variable name. Each value can be:
  1. A direct value (number/string).
  2. A reference to an existing variable: use the syntax "${variable_name}".
  3. A template string that interpolates variables for string concatenation.
     - Example: "The reason is: ${reason}, and the solution is: ${solution}"
  4. A basic arithmetic expression involving numeric variables:
     - Supported operators: +, -, *, /, ** (pow), % (mod), unary +/-
     - Example: "${var0} / 3 + ${var1}"

The VM will:
1. Replace each "${varName}" with the current value of varName.
2. If the result is a pure numeric expression (e.g., 2+3, 5*6, or referencing numeric variables), it will be evaluated as a number.
3. If the result is a string with placeholders, it becomes a string concatenation or template filling.
4. Assign the final computed result back to the target variable(s).


**Examples:**

1. Direct Assignment
   ```json
   {
     "seq_no": 0,
     "type": "assign",
     "parameters": {
       "constant_number": 42,
       "message": "Hello World"
     }
   }
   ```

2. Template/String Interpolation
   ```json
   {
     "seq_no": 1,
     "type": "assign",
     "parameters": {
       "recommended_solution": "Reason: ${reason}\nSolution: ${solution}"
     }
   }
   ```

3. Basic Arithmetic
   ```json
   {
     "seq_no": 2,
     "type": "assign",
     "parameters": {
       "calculated_result": "${num1} + ${num2} / 3"
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
- **Language Consistency**: All the instructions (e.g. `llm_generate`) that directly contribute to generating the `final_answer` must be written in the same language as the goal. This ensures the final output is consistent with the intended language.

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

- **Final Answer Alignment**:
  - **Goal-Centric Generation**: Ensure that the generated `final_answer` directly addresses the question or objective outlined in the goal. The `final_answer` should be focused and relevant to the goal and avoid general response.
  - **Contextual Consistency**: Since the tools in the plan (e.g., `llm_generate`) do not aware the goal, include the goal context when making tool calls if necessary. Maintain the alignment between the goal and all intermediate steps leading to the `final_answer`. This ensures that every instruction and tool interaction contributes towards achieving the desired outcome.
  - **Avoid Divergence**: Prevent the generation of information that, while relevant, does not serve to answer the primary goal. All synthesized and summarized data should reinforce the goal-centric `final_answer`.

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



## 9. Available Tools for `calling` instruction


Please use only the following tools in Calling Instruction:

### retrieve_knowledge_graph


    Retrieves TiDB related information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

    Arguments:
    - `query`: The query string. Can be a direct string or a variable reference.

    Output:
    - Returns a single value representing the retrieved knowledge graph data.


    Best practices:
    - Focus on Structured Knowledge: Use the retrieve_knowledge_graph tool to retrieve structured and relational knowledge that is relevant to the query. This tool excels in identifying fine-grained knowledge points and understanding their connections.
    - Combine with LLM for Refinement:
        - Knowledge Graph Search may return extensive data, including numerous nodes and complex relationships.
        - Always follow up with an LLM generation tool to refine and summarize the results. This ensures the output is concise, precise, and tailored to the user's question.

    Strict Restriction:
    - Avoid User-Specific Queries: Do not use this tool to retrieve data that is specific to a user's environment, such as configurations, current versions, or private data. This tool is designed to handle general, shared knowledge within the graph.
    

### llm_generate


    Generates a response using the Language Model (LLM).

    This tool must be used within a "calling" instruction in the plan.

    Arguments:
    - `prompt`: The prompt to provide to the LLM. Can be a direct string or a variable reference.
        - **Language Matching**: Write the prompt in the same language as the goal.
        - **Language Confirmation**: Append a sentence to confirm the desired language of the generated text:
            - *For English goals*: "Please ensure that the generated text uses English."
            - *For Chinese goals*: "请确保生成的文本使用中文。"
            - *For Japanese goals*: "Please ensure that the generated text uses Japanese."
    - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.

    Output: The output format (text or JSON) depends on your instructions.
    - Text Response: If you ask for a text answer, let output_vars be an array containing one variable name. The entire text response will be stored under this variable.
    - JSON Response: If you instruct the LLM to respond in JSON format, let output_vars be an array containing variable names that match the keys in the JSON response. Each variable name corresponds to a key in the JSON object, and the value associated with each key is stored under the corresponding variable name.

    Example usage in a plan:
    ```json
    {
        "seq_no": 1,
        "type": "calling",
        "parameters": {
            "tool_name": "llm_generate",
            "tool_params": {
                "prompt": "Analyze the sales data and provide summary and insights, response a json object including keys ['summary', 'insights'].",
                "context": "${sales_data}"
            },
            "output_vars": ["summary", "insights"]
        }
    }
    ```

    Best practices:
    - Always use llm_generate within a "calling" instruction in your plan.
    - Use variable references (${variable_name}) when you need to include dynamic content from previous steps.
    

### vector_search


    Retrieves the most relevant TiDB Document data chunks based on embedding similarity to the query.

    Arguments:
    - `query`: The query string. It should be a clear and simple statement or question, focusing on a single objective.
    - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.

    Output:
    - Returns a single value containing the concatenated top `k` document chunks, stored in a unique variable. It does not return a JSON or dictionary object.

    Example to call this tool:

    **Example:**
    ```json
    {
        "seq_no": 3,
        "type": "calling",
        "parameters": {
            "tool_name": "vector_search",
            "tool_params": {
                "query": "Information about ...",
                "top_k": 10
            },
            "output_vars": ["embedded_chunks"]
        }
    }
    ```

    Best practices:
    - Use the Vector Search tool to retrieve data that is most similar to your query based on embedding distance. This tool excels at finding relevant document snippets that provide rich context and detailed information.
    - **Ensure your query is clear and focused on a single objective or aspect.** Avoid queries with multiple purposes to achieve the most accurate and relevant results.
    - Do not insert the raw results from vector_search directly into the final_answer. The vector search tool returns arrays or multiple document fragments that may not be immediately suitable for a coherent final response. Instead, first use an LLM generation step to summarize, refine, and unify the language of these fragments. Once processed into a concise and well-structured text in the target language, then integrate this refined output into the final_answer.
    



## 10. Example: Here are an example how to handle a similar task.

### The approach

Refer the best practices and example

###  Plan Example

**Goal**:
What is TiDB?
**The plan:**
[{'parameters': {'chain_of_thoughts': 'To understand what TiDB is, we will follow a structured approach: 1. Search for TiDB from multiple aspects such as its purpose, key features, technical details, and use cases. 2. For each aspect, use the knowledge graph to retrieve structured information and vector search to gather detailed information from unstructured data. 3. Use an LLM to synthesize the information from both sources for each aspect. 4. Collect the summaries of multiple aspects and generate a final comprehensive answer.', 'dependency_analysis': 'Each aspect involves retrieving structured and unstructured data, followed by synthesis. The final step combines all synthesized information into a comprehensive explanation.'}, 'seq_no': 0, 'type': 'reasoning'}, {'parameters': {'output_vars': ['tidb_purpose_knowledge_graph'], 'tool_name': 'retrieve_knowledge_graph', 'tool_params': {'query': 'TiDB purpose'}}, 'seq_no': 1, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_purpose_vector_info'], 'tool_name': 'vector_search', 'tool_params': {'query': 'What is the purpose of TiDB?', 'top_k': 3}}, 'seq_no': 2, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_purpose_explanation'], 'tool_name': 'llm_generate', 'tool_params': {'context': 'Knowledge Graph Data: ${tidb_purpose_knowledge_graph}\nVector Search Data: ${tidb_purpose_vector_info}', 'prompt': 'Using the information from the knowledge graph and vector search, provide a detailed explanation of the purpose of TiDB. Please ensure that the generated text uses English.'}}, 'seq_no': 3, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_features_knowledge_graph'], 'tool_name': 'retrieve_knowledge_graph', 'tool_params': {'query': 'TiDB key features'}}, 'seq_no': 4, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_features_vector_info'], 'tool_name': 'vector_search', 'tool_params': {'query': 'What are the key features of TiDB?', 'top_k': 3}}, 'seq_no': 5, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_features_explanation'], 'tool_name': 'llm_generate', 'tool_params': {'context': 'Knowledge Graph Data: ${tidb_features_knowledge_graph}\nVector Search Data: ${tidb_features_vector_info}', 'prompt': 'Using the information from the knowledge graph and vector search, provide a detailed explanation of the key features of TiDB. Please ensure that the generated text uses English.'}}, 'seq_no': 6, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_technical_details_knowledge_graph'], 'tool_name': 'retrieve_knowledge_graph', 'tool_params': {'query': 'TiDB technical details'}}, 'seq_no': 7, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_technical_details_vector_info'], 'tool_name': 'vector_search', 'tool_params': {'query': 'What are the technical details of TiDB?', 'top_k': 3}}, 'seq_no': 8, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_technical_details_explanation'], 'tool_name': 'llm_generate', 'tool_params': {'context': 'Knowledge Graph Data: ${tidb_technical_details_knowledge_graph}\nVector Search Data: ${tidb_technical_details_vector_info}', 'prompt': 'Using the information from the knowledge graph and vector search, provide a detailed explanation of the technical details of TiDB. Please ensure that the generated text uses English.'}}, 'seq_no': 9, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_use_cases_knowledge_graph'], 'tool_name': 'retrieve_knowledge_graph', 'tool_params': {'query': 'TiDB use cases'}}, 'seq_no': 10, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_use_cases_vector_info'], 'tool_name': 'vector_search', 'tool_params': {'query': 'What are the use cases of TiDB?', 'top_k': 3}}, 'seq_no': 11, 'type': 'calling'}, {'parameters': {'output_vars': ['tidb_use_cases_explanation'], 'tool_name': 'llm_generate', 'tool_params': {'context': 'Knowledge Graph Data: ${tidb_use_cases_knowledge_graph}\nVector Search Data: ${tidb_use_cases_vector_info}', 'prompt': 'Using the information from the knowledge graph and vector search, provide a detailed explanation of the use cases of TiDB. Please ensure that the generated text uses English.'}}, 'seq_no': 12, 'type': 'calling'}, {'parameters': {'output_vars': ['final_answer'], 'tool_name': 'llm_generate', 'tool_params': {'context': 'Purpose: ${tidb_purpose_explanation}\nFeatures: ${tidb_features_explanation}\nTechnical Details: ${tidb_technical_details_explanation}\nUse Cases: ${tidb_use_cases_explanation}', 'prompt': 'Combine the explanations of the purpose, key features, technical details, and use cases of TiDB into a comprehensive answer. Please ensure that the generated text uses English.'}}, 'seq_no': 13, 'type': 'calling'}]


**Note**: Examples are to provide the ideas and examples for solving similar problems. Please do not use tools that appear in the example but do not appear in Available Tools for `calling` instruction. You can find more suitable tools in Available Tools for `calling` instruction to achieve the goal.

-------------------------------

Now, let's generate the plan for goal: does tidb support sql? {'lang': 'Japanese'}

1. **Analyze the Request**:
   - Determine the primary intent behind the goal.
   - Identify any implicit requirements or necessary prerequisites.

2. **Break Down the Goal**:
   - Decompose the goal into smaller, manageable sub-goals or tasks.
   - Ensure each sub-goal is specific, actionable, and can be addressed with existing tools or data sources.
   - Identify dependencies between sub-goals to establish the correct execution order.

3. **Generate an Action Plan**:
   - For each sub-goal, create a corresponding action step to achieve it.
   - Ensure the plan follows the VM Specification.
   - Include a 'reasoning' step at the beginning of the plan that outlines the chain of thought and dependency analysis of the steps.
   - IMPORTANT: Always use tools within "calling" instructions. Never use tool functions directly in the plan.

4. **Tool Usage Guidelines**:
   - When using a tool, always wrap it in a "calling" instruction.
   - For calling instruction, **Only select tools listed in the "Available Tools for `calling` instruction" section**. Using tools outside this list will cause the plan to fail.
   - The "calling" instruction should have the following structure:
     ```json
     {
       "seq_no": <unique_sequential_number>,
       "type": "calling",
       "parameters": {
         "tool_name": "<tool_name>",
         "tool_params": {
           <tool-specific parameters>
         },
         "output_vars": [<list_of_output_variable_names>]
       }
     }
     ```
   - Ensure that the "tool_params" object contains all necessary parameters for the specific tool being called.

The final step of the plan must be assign the final output result to the 'final_answer' variable.
Please provide only the JSON array for the action plan without any additional text, explanations, or markdown. 
Ensure the JSON is properly formatted and encapsulated within a ```json code block.

    ```json
    [
      {
        "seq_no": 0,
        "type": "reasoning",
        "parameters": {
          "chain_of_thoughts": "...",
          "dependency_analysis": "..."
        }
      },
      ...
    ]