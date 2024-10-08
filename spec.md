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
- **Plan Parsing**: Plans are provided in JSON format and parsed by the VM.

## 2. Instruction Format
Each instruction in the plan is represented as a JSON object with the following keys:

- `seq_no`: A unique integer identifying the instruction's sequence within the plan.
- `type`: A string indicating the instruction type.
- `parameters`: An object containing parameters required by the instruction.

{
  "seq_no": 0,
  "type": "instruction_type",
  "parameters": {
    "param1": "value_or_variable_reference",
    "param2": "value_or_variable_reference",
    "..."
  }
}

## 3. Supported Instructions
1. assign
Purpose: Assigns a value to a variable.

Parameters:

value: The value to assign. Can be a direct value or a variable reference.
var_name: The name of the variable to assign the value to.
Example:

{
  "seq_no": 0,
  "type": "assign",
  "parameters": {
    "value": 42,
    "var_name": "number"
  }
}
2. llm_generate
Purpose: Generates a response using the Language Model (LLM).

Parameters:

prompt: The prompt to provide to the LLM. Can be a direct string or a variable reference.
context (optional): Additional context for the LLM. Can be a direct string or a variable reference.
output_var: The name of the variable to store the LLM's output.
Example:

{
  "seq_no": 1,
  "type": "llm_generate",
  "parameters": {
    "prompt": "What is the capital of France?",
    "context": null,
    "output_var": "llm_output"
  }
}
3. retrieve_knowledge_graph
Purpose: Retrieves information from a knowledge graph based on a query.

Parameters:

query: The query string. Can be a direct string or a variable reference.
output_var: The name of the variable to store the retrieved data.
Example:

{
  "seq_no": 2,
  "type": "retrieve_knowledge_graph",
  "parameters": {
    "query": "Tallest mountain in the world",
    "output_var": "knowledge_data"
  }
}
4. retrieve_embedded_chunks
Purpose: Retrieves embedded knowledge chunks based on an embedding query.

Parameters:

embedding_query: The embedding query string. Can be a direct string or a variable reference.
top_k: The number of top chunks to retrieve. Can be a direct integer or a variable reference.
output_var: The name of the variable to store the retrieved chunks.
Example:

{
  "seq_no": 3,
  "type": "retrieve_embedded_chunks",
  "parameters": {
    "embedding_query": "Information about Mount Everest",
    "top_k": 3,
    "output_var": "embedded_chunks"
  }
}
5. condition
Purpose: Evaluates a condition using the LLM and executes one of two branches based on the result.

Parameters:

prompt: The condition prompt to provide to the LLM. Can be a direct string or a variable reference.
context (optional): Additional context for the LLM. Can be a direct string or a variable reference.
true_branch: A list of instructions to execute if the condition evaluates to true.
false_branch: A list of instructions to execute if the condition evaluates to false.
Example:

{
  "seq_no": 4,
  "type": "condition",
  "parameters": {
    "prompt": "Is {{number}} even? Respond with 'true' or 'false'.",
    "context": null,
    "true_branch": [
      {
        "seq_no": 5,
        "type": "assign",
        "parameters": {
          "value": "The number is even.",
          "var_name": "result"
        }
      }
    ],
    "false_branch": [
      {
        "seq_no": 6,
        "type": "assign",
        "parameters": {
          "value": "The number is odd.",
          "var_name": "result"
        }
      }
    ]
  }
}
6. reasoning
Purpose: Provides a detailed chain of thoughts of the plan's reasoning, analysis, and steps.

Parameters:

chain_of_thoughts: A string containing the reasoning and analysis for the plan.
dependency_analysis: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

Example:

{
  "seq_no": 7,
  "type": "reasoning",
  "parameters": {
    "chain_of_thoughts": "...",
    "dependency_analysis": "..."
  }
}

## 4. Parameters and Variable References
Parameters can be either direct values or variable references. To reference a variable, use a dictionary with the key "var" and the variable name as the value.

Direct Value Example:

"prompt": "What is the capital of France?"

Variable Reference Example:

"prompt": { "var": "user_question" }

When the VM encounters a variable reference, it will replace it with the value stored in the variable store under that name.

## 5. Variables and Dependencies
Variable Assignment: Use the assign instruction or specify an output_var in instructions that produce outputs.
Variable Access: Reference variables in parameters using the variable reference format.
Dependencies: Manage dependencies by assigning outputs to variables and referencing them in subsequent instructions.

## 6. Plan Structure
- Sequential Execution: Instructions are executed in order based on their `seq_no`.
- Control Flow: Use the condition instruction for branching logic.
- Subplans: Branches in a condition instruction are subplans (lists of instructions) with their own `seq_no` values.

## 7. Best Practices
- Sequence Numbering: Ensure that `seq_no` values are unique and sequential within the main plan and any subplans.
- Variable Naming: Use descriptive variable names to make the plan readable and maintainable.

## 8. Example Plan
Goal: Provide best practices for optimizing TiDB performance for a high-volume e-commerce application, considering the latest stable version of TiDB.

The plan:
[
  {
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {
      "chain_of_thoughts": "To answer this question, we will:\n1. Determine the latest stable version of TiDB.\n2. Retrieve general information about the latest TiDB from the knowledge graph.\n3. Use the vector database to find relevant performance optimization techniques for the latest version.\n4. Retrieve specific e-commerce related optimizations from the knowledge graph.\n5. Combine and synthesize the information using the LLM.\n6. Compile the final answer.",
      "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 1.\nStep 5 depends on Steps 2, 3, and 4.\nStep 6 depends on Step 5."
    }
  },
  {
    "seq_no": 1,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "What is the latest stable version of TiDB?",
      "output_var": "latest_tidb_version"
    }
  },
  {
    "seq_no": 2,
    "type": "condition",
    "parameters": {
      "prompt": "Was a specific latest stable version of TiDB found? Answer 'true' or 'false'.",
      "context": "Latest TiDB version: {{latest_tidb_version}}",
      "true_branch": [
        {
          "seq_no": 3,
          "type": "retrieve_knowledge_graph",
          "parameters": {
            "query": "What are the key features and improvements in TiDB version {{latest_tidb_version}}?",
            "output_var": "tidb_info"
          }
        }
      ],
      "false_branch": [
        {
          "seq_no": 4,
          "type": "retrieve_embedded_chunks",
          "parameters": {
            "embedding_query": "Latest TiDB version and its key features",
            "top_k": 3,
            "output_var": "tidb_info"
          }
        }
      ]
    }
  },
  {
    "seq_no": 5,
    "type": "retrieve_embedded_chunks",
    "parameters": {
      "embedding_query": "TiDB {{latest_tidb_version}} performance optimization techniques",
      "top_k": 5,
      "output_var": "performance_techniques"
    }
  },
  {
    "seq_no": 6,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "What are specific considerations for optimizing TiDB {{latest_tidb_version}} for e-commerce applications?",
      "output_var": "ecommerce_optimizations"
    }
  },
  {
    "seq_no": 7,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Based on the following information for TiDB version {{latest_tidb_version}}:\n1. TiDB Overview: {{tidb_info}}\n2. General Performance Techniques: {{performance_techniques}}\n3. E-commerce Specific Optimizations: {{ecommerce_optimizations}}\n\nProvide a comprehensive list of best practices for optimizing TiDB performance for a high-volume e-commerce application. Organize the recommendations into categories such as schema design, indexing, query optimization, and infrastructure scaling. Ensure that all recommendations are applicable to TiDB version {{latest_tidb_version}}.",
      "context": null,
      "output_var": "final_recommendations"
    }
  },
  {
    "seq_no": 8,
    "type": "assign",
    "parameters": {
      "value": "Best practices for optimizing TiDB {{latest_tidb_version}} performance for a high-volume e-commerce application:\n\n{{final_recommendations}}",
      "var_name": "final_answer"
    }
  }
]
