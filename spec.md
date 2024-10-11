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
Purpose: Retrieves information from a knowledge graph based on a query, returning nodes and relationships between those nodes.

Parameters:

query: The query string. Can be a direct string or a variable reference.
output_var: The name of the variable to store the retrieved graph data.

Example:

{
  "seq_no": 2,
  "type": "retrieve_knowledge_graph",
  "parameters": {
    "query": "TiDB latest stable version",
    "output_var": "tidb_version_graph"
  }
}

Note: This instruction returns a graph structure containing nodes and relationships, not a direct answer. Further processing (e.g., using llm_generate) is typically required to extract specific information from the returned graph data.
4. vector_search
Purpose: Retrieves embedded knowledge chunks based on an embedding query.

Parameters:

vector_search: The query string. Can be a direct string or a variable reference.
top_k: The number of top chunks to retrieve. Can be a direct integer or a variable reference.
output_var: The name of the variable to store the retrieved chunks.
Example:

{
  "seq_no": 3,
  "type": "vector_search",
  "parameters": {
    "vector_search": "Information about Mount Everest",
    "top_k": 3,
    "output_var": "embedded_chunks"
  }
}
5. jmp_if
   Purpose: Conditionally jumps to specified sequence numbers based on the evaluation of a condition using the LLM.

   Parameters:
   - `condition_prompt`: The prompt to evaluate the condition. Can be a direct string or a variable reference.
   - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.
   - `jump_if_true`: The `seq_no` to jump to if the condition evaluates to true.
   - `jump_if_false`: The `seq_no` to jump to if the condition evaluates to false.

   Example:

   {
     "seq_no": 4,
     "type": "jmp_if",
     "parameters": {
       "condition_prompt": "Is {{number}} even? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if the number is even, false otherwise, and 'explanation' provides a brief reason for the result.",
       "context": null,
       "jump_if_true": 5,
       "jump_if_false": 6
     }
   }
6. jmp
   Purpose: Unconditionally jumps to a specified sequence number.

   Parameters:
   - target_seq: The seq_no to jump to.

   Usage:
   - The `jmp` instruction can be used in conjunction with `jmp_if` to manage conditional logic effectively. After a `jmp_if` instruction determines which branch to take, a `jmp` can be used to skip over the alternative branch that should not be executed. This ensures that only the relevant steps are processed, optimizing the execution flow.

   Example:

   {
     "seq_no": 4,
     "type": "jmp",
     "parameters": {
       "target_seq": 6
     }
   }
7. reasoning
Purpose: Provides a detailed explanation of the plan's reasoning process, analysis, and steps.

Parameters:

chain_of_thoughts: A string containing a comprehensive breakdown of the reasoning process behind the plan. This should include:
  - The overall strategy for approaching the problem
  - Key decision points and rationale for choices made
  - Assumptions and their justifications
  - Potential alternative approaches considered
  - Expected outcomes of each major step
  - How different pieces of information are intended to be combined
  - Any limitations or potential issues with the chosen approach

dependency_analysis: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

Example:

{
  "seq_no": 0,
  "type": "reasoning",
  "parameters": {
    "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach:

    1. Overall Strategy:
       We'll first determine the latest stable version of TiDB, then gather relevant information about its features and optimization techniques, with a focus on e-commerce applications.

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
    "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 1.\nSteps 4-8 depend on the outcome of Step 3.\nStep 9 depends on Steps 4-8.\nStep 10 depends on Step 9."
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
- Control Flow: Use the `jmp_if` and `jmp` instructions for branching logic and conditional loops.

## 7. Best Practices
- Sequence Numbering: Ensure that `seq_no` values are unique and sequential within the plan.
- Variable Naming: Use descriptive variable names to make the plan readable and maintainable.
- Control Flow: Use `jmp_if` and `jmp` instructions to create conditional logic, manage execution flow, and implement loops effectively.

## 8. Example Plan
Goal: Provide best practices for optimizing TiDB performance for a high-volume e-commerce application, considering the latest stable version of TiDB.

The plan:
[
  {
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {
      "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach:

      1. Overall Strategy:
         We'll first determine the latest stable version of TiDB, then gather relevant information about its features and optimization techniques, with a focus on e-commerce applications.

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
      "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 1.\nSteps 4-8 depend on the outcome of Step 3.\nStep 9 depends on Steps 4-8.\nStep 10 depends on Step 9."
    }
  },
  {
    "seq_no": 1,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "TiDB latest stable version",
      "output_var": "tidb_version_graph"
    }
  },
  {
    "seq_no": 2,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Analyze the following knowledge graph data about TiDB versions:\n{{tidb_version_graph}}\n\nExtract and return the latest stable version number of TiDB. If you can't determine the exact version, return 'Unknown'.",
      "context": null,
      "output_var": "latest_tidb_version"
    }
  },
  {
    "seq_no": 3,
    "type": "jmp_if",
    "parameters": {
      "condition_prompt": "Was a specific latest stable version of TiDB found? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if a specific version was found, false otherwise, and 'explanation' provides a brief reason for the result.",
      "context": "Latest TiDB version: {{latest_tidb_version}}",
      "jump_if_true": 4,
      "jump_if_false": 6
    }
  },
  {
    "seq_no": 4,
    "type": "vector_search",
    "parameters": {
      "query": "What are the key features and improvements in TiDB version {{latest_tidb_version}}?",
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
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "vector_search": "Latest TiDB version and its key features",
      "top_k": 3,
      "output_var": "tidb_info"
    }
  },
  {
    "seq_no": 7,
    "type": "vector_search",
    "parameters": {
      "vector_search": "TiDB {{latest_tidb_version}} performance optimization techniques",
      "top_k": 5,
      "output_var": "performance_techniques"
    }
  },
  {
    "seq_no": 8,
    "type": "vector_search",
    "parameters": {
      "query": "What are specific considerations for optimizing TiDB {{latest_tidb_version}} for e-commerce applications?",
      "output_var": "ecommerce_optimizations"
    }
  },
  {
    "seq_no": 9,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Based on the following information for TiDB version {{latest_tidb_version}}:\n1. TiDB Overview: {{tidb_info}}\n2. General Performance Techniques: {{performance_techniques}}\n3. E-commerce Specific Optimizations: {{ecommerce_optimizations}}\n\nProvide a comprehensive list of best practices for optimizing TiDB performance for a high-volume e-commerce application. Organize the recommendations into categories such as schema design, indexing, query optimization, and infrastructure scaling. Ensure that all recommendations are applicable to TiDB version {{latest_tidb_version}}.",
      "context": null,
      "output_var": "final_recommendations"
    }
  },
  {
    "seq_no": 10,
    "type": "assign",
    "parameters": {
      "value": "Best practices for optimizing TiDB {{latest_tidb_version}} performance for a high-volume e-commerce application:\n\n{{final_recommendations}}",
      "var_name": "final_answer"
    }
  }
]