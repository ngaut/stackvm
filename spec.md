# Specification for Generating Executable Plans for the Stack-Based Virtual Machine (VM)

## Table of Contents
1. Overview of the Stack-Based VM
2. Instruction Format
3. Supported Instructions
4. Parameters and Variable References
5. Variables and Dependencies
6. Plan Structure
7. Best Practices
8. Example Plan
9. Error Handling and Adjustments

## 1. Overview of the Stack-Based VM
The Stack-Based VM executes plans consisting of a sequence of instructions. Each instruction performs a specific operation and may interact with variables stored in a variable store. The VM supports conditional execution and can handle dependencies between instructions through variable assignments and references.

### Key features:
- **Variable Store**: A key-value store where variables are stored and accessed by name.
- **Instruction Execution**: Instructions are executed sequentially unless control flow is altered by conditional statements.
- **Plan Parsing**: Plans are provided in JSON format and parsed by the VM.
- **Error Handling**: The VM logs errors and can adjust plans based on execution failures.

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
Purpose: Provides a detailed explanation(chain of thoughts) of the plan's reasoning, analysis, and steps.

Parameters:

chain_of_thoughts: A string containing the reasoning and analysis for the plan.
dependency_analysis: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

Example:

{
  "seq_no": 7,
  "type": "reasoning",
  "parameters": {
    "chain_of_thoughts": "To determine the population of the capital city of the third largest neighboring country of France by area, we will follow these steps:\n1. Retrieve a list of France's neighboring countries sorted by area.\n2. Identify the third largest country from this list.\n3. Find the capital city of the identified country.\n4. Retrieve population data for the capital city.\n5. Extract and validate the population number.\n6. Format the final answer.",
    "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2.\nStep 4 depends on Step 3.\nStep 5 depends on Step 4.\nStep 6 depends on Step 5."
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
- Error Handling: Anticipate possible failures and structure the plan to handle them gracefully.
- Contextual Prompts: Provide sufficient context to the LLM in prompts to ensure accurate responses.
- Consistency: Maintain a consistent structure and format throughout the plan.
- Testing: Verify the plan for syntax correctness and logical flow before execution.

## 8. Example Plan
Goal: Determine the population of the capital city of the third largest neighboring country of France by area.

The plan:
[
  {
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {
      "chain of thoughts": "To determine the population of the capital city of the third largest neighboring country of France by area, we will follow these steps:\n1. Retrieve a list of France's neighboring countries sorted by area.\n2. Identify the third largest country from this list.\n3. Find the capital city of the identified country.\n4. Retrieve population data for the capital city.\n5. Extract and validate the population number.\n6. Format the final answer."
    }
  },
  {
    "seq_no": 1,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "Countries neighboring France sorted by area in descending order",
      "output_var": "france_neighbors"
    }
  },
  {
    "seq_no": 2,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Given this list of France's neighboring countries sorted by area: {{france_neighbors}}, what is the name of the third largest country?",
      "context": null,
      "output_var": "third_largest_country"
    }
  },
  {
    "seq_no": 3,
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "Capital city of {{third_largest_country}}",
      "output_var": "capital_city"
    }
  },
  {
    "seq_no": 4,
    "type": "retrieve_embedded_chunks",
    "parameters": {
      "embedding_query": "Population of {{capital_city}}",
      "top_k": 3,
      "output_var": "population_data"
    }
  },
  {
    "seq_no": 5,
    "type": "llm_generate",
    "parameters": {
      "prompt": "Based on this information: {{population_data}}, what is the current population of {{capital_city}}? Provide only the number.",
      "context": null,
      "output_var": "population_number"
    }
  },
  {
    "seq_no": 6,
    "type": "condition",
    "parameters": {
      "prompt": "Is {{population_number}} a valid number? Respond with 'true' or 'false'.",
      "context": null,
      "true_branch": [
        {
          "seq_no": 7,
          "type": "assign",
          "parameters": {
            "value": "The population of {{capital_city}}, the capital of {{third_largest_country}} (the third largest neighboring country of France by area), is {{population_number}}.",
            "var_name": "final_answer"
          }
        }
      ],
      "false_branch": [
        {
          "seq_no": 8,
          "type": "llm_generate",
          "parameters": {
            "prompt": "The population number {{population_number}} seems invalid. Please provide a reasonable estimate for the population of {{capital_city}}, the capital of {{third_largest_country}}.",
            "context": null,
            "output_var": "estimated_population"
          }
        },
        {
          "seq_no": 9,
          "type": "assign",
          "parameters": {
            "value": "The estimated population of {{capital_city}}, the capital of {{third_largest_country}} (the third largest neighboring country of France by area), is approximately {{estimated_population}}.",
            "var_name": "final_answer"
          }
        }
      ]
    }
  }
]

## 9. Error Handling and Adjustments
If an instruction fails (e.g., due to invalid parameters or runtime errors), the VM logs the error.
The VM may attempt to adjust the plan based on the errors by requesting a new plan from the LLM.
To assist in adjustments, ensure that error messages are informative and that the plan is structured to allow for retries or alternative strategies.