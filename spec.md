# Specification for Generating Executable Plans for the Virtual Machine (VM)

## Table of Contents
1. Overview of the VM
2. Instruction Format
3. Supported Instructions
4. Parameters and Variable References
5. Variables and Dependencies
6. Plan Structure
7. Best Practices
8. Example Plan

## 1. Overview of the VM
The VM executes plans consisting of a sequence of instructions. Each instruction performs a specific operation and may interact with variables stored in a variable store. The VM supports conditional execution and can handle dependencies between instructions through variable assignments and references.

### Key features:
- **Variable Store**: A key-value store where variables are stored and accessed by name.
- **Instruction Execution**: Instructions are executed sequentially unless control flow is altered by conditional statements.

## 2. Instruction Format
Each instruction in the plan is represented as a JSON object with the following keys:

- `seq_no`: A unique and AUTO-INCREMENT integer identifying the instruction's sequence within the plan, starts from 0.
- `type`: A string indicating the instruction type.
- `parameters`: An object containing parameters required by the instruction.

```json
{
  "seq_no": 0,
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
  "seq_no": 0,
  "type": "assign",
  "parameters": {
    "number": 42,
    "doubled_number": "${number}"
  }
}
```

### 3.2 llm_generate
- **Purpose**: Generates a response using the Language Model (LLM).
- **Parameters**: 
  - `prompt`: The prompt to provide to the LLM. Can be a direct string or a variable reference.
  - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.
  - `output_var`: The name of the variable to store the LLM's output.

**Example:**
```json
{
  "seq_no": 1,
  "type": "llm_generate",
  "parameters": {
    "prompt": "What is the capital of France?",
    "context": null,
    "output_var": "llm_output"
  }
}
```

### 3.3 retrieve_knowledge_graph
- **Purpose**: Retrieves information from a knowledge graph based on a query, returning nodes and relationships between those nodes.
- **Parameters**:
  - `query`: The query string. Can be a direct string or a variable reference.
  - `output_var`: The name of the variable to store the retrieved graph data.

**Example:**
```json
{
  "seq_no": 2,
  "type": "retrieve_knowledge_graph",
  "parameters": {
    "query": "TiDB latest stable version",
    "output_var": "tidb_version_graph"
  }
}
```

### 3.4 vector_search
- **Purpose**: Retrieves embedded knowledge chunks based on an embedding query.
- **Parameters**:
  - `query`: The query string. Can be a direct string or a variable reference.
  - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.
  - `output_var`: The name of the variable to store the retrieved chunks.

**Example:**
```json
{
  "seq_no": 3,
  "type": "vector_search",
  "parameters": {
    "query": "Information about Mount Everest",
    "top_k": 3,
    "output_var": "embedded_chunks"
  }
}
```

### 3.5 jmp_if
- **Purpose**: Conditionally jumps to specified sequence numbers based on the evaluation of a condition using the LLM.
- **Parameters**:
  - `condition_prompt`: The prompt to evaluate the condition. **Must respond with a JSON object in the following format:**
    ```json
    {
      "result": boolean,
      "explanation": string
    }
    ```
  - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.
  - `jump_if_true`: The `seq_no` to jump to if the condition evaluates to true.
  - `jump_if_false`: The `seq_no` to jump to if the condition evaluates to false.

**Example:**
```json
{
  "seq_no": 4,
  "type": "jmp_if",
  "parameters": {
    "condition_prompt": "Is ${number} even? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if the number is even, false otherwise, and 'explanation' provides a brief reason for the result.",
    "context": null,
    "jump_if_true": 5,
    "jump_if_false": 6
  }
}
```

### 3.6 jmp
- **Purpose**: Unconditionally jumps to a specified sequence number.
- **Parameters**:
  - `target_seq`: The seq_no to jump to.

**Example:**
```json
{
  "seq_no": 5,
  "type": "jmp",
  "parameters": {
    "target_seq": 7
  }
}
```

### 3.7 reasoning
- **Purpose**: Provides a detailed explanation of the plan's reasoning process, analysis, and steps.
- **Parameters**:
  - `chain_of_thoughts`: A string containing a comprehensive breakdown of the reasoning process.
  - `dependency_analysis`: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

**Example:**
```json
{
  "seq_no": 0,
  "type": "reasoning",
  "parameters": {
    "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach...",
    "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2..."
  }
}
```

## 4. Parameters and Variable References
Parameters can be either direct values or variable references. To reference a variable, use the format `${variable_name}`.

**Direct Value Example:**
```json
"prompt": "What is the capital of France?"
```

**Variable Reference Example:**
```json
"prompt": "${user_question}"
```

## 5. Variables and Dependencies
- **Variable Assignment**: Use the `assign` instruction or specify an `output_var` in instructions that produce outputs.
- **Variable Access**: Reference variables in parameters using the variable reference format.
- **Dependencies**: Manage dependencies by assigning outputs to variables and referencing them in subsequent instructions.

## 6. Plan Structure
- **Sequential Execution**: Instructions are executed in order based on their `seq_no`.
- **Control Flow**: Use the `jmp_if` and `jmp` instructions for branching logic and conditional loops.

## 7. Best Practices
- **Sequence Numbering**: Ensure that `seq_no` values are unique and sequential within the plan.
- **Variable Naming**: Use descriptive variable names to make the plan readable and maintainable.
- **Control Flow**: Use `jmp_if` and `jmp` instructions to create conditional logic, manage execution flow, and implement loops effectively.

## 8. Example Plan
**Goal**: Provide best practices for optimizing TiDB performance for a high-volume e-commerce application, considering the latest stable version of TiDB.

**The plan:**
```json
[
  {
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {
      "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach...",
      "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2..."
    }
  },
  {
    "seq_no": 1,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "TiDB latest stable version",
      "output_var": "latest_tidb_version_info"
    }
  },
  {
    "seq_no": 2,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Analyze the provided knowledge graph data to extract the latest stable version number of TiDB...",
      "context": "the retrieved knowledge graph data:\n${latest_tidb_version_info}",
      "output_var": "latest_tidb_version"
    }
  },
  {
    "seq_no": 3,
    "type": "jmp_if",
    "parameters": {
      "condition_prompt": "Was a specific latest stable version of TiDB found? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if a specific version was found, false otherwise, and 'explanation' provides a brief reason for the result.",
      "context": "Latest TiDB version: ${latest_tidb_version}",
      "jump_if_true": 4,
      "jump_if_false": 6
    }
  },
  {
    "seq_no": 4,
    "type": "vector_search",
    "parameters": {
      "query": "What are the key features and improvements in TiDB version ${latest_tidb_version}?",
      "top_k": 3,
      "output_var": "tidb_info"
    }
  },
  {
    "seq_no": 5,
    "type": "jmp",
    "parameters": {
      "target_seq": 7
    }
  },
  {
    "seq_no": 6,
    "type": "vector_search",
    "parameters": {
      "query": "Latest TiDB version and its key features",
      "top_k": 3,
      "output_var": "tidb_info"
    }
  },
  {
    "seq_no": 7,
    "type": "vector_search",
    "parameters": {
      "query": "TiDB ${latest_tidb_version} performance optimization techniques",
      "top_k": 5,
      "output_var": "performance_techniques"
    }
  },
  {
    "seq_no": 8,
    "type": "vector_search",
    "parameters": {
      "query": "What are specific considerations for optimizing TiDB ${latest_tidb_version} for e-commerce applications?",
      "output_var": "ecommerce_optimizations"
    }
  },
  {
    "seq_no": 9,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Provide a comprehensive list of best practices for optimizing TiDB performance for a high-volume e-commerce application...",
      "context": "Based on the following information for TiDB version ${latest_tidb_version}:\n1. TiDB Overview: ${tidb_info}\n2. General Performance Techniques: ${performance_techniques}\n3. E-commerce Specific Optimizations: ${ecommerce_optimizations}",
      "output_var": "final_recommendations"
    }
  },
  {
    "seq_no": 10,
    "type": "assign",
    "parameters": {
      "result": "Best practices for optimizing TiDB ${latest_tidb_version} performance for a high-volume e-commerce application:\n\n${final_recommendations}"
    }
  }
]
