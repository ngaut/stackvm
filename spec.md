Specification for Generating Executable Plans for the Stack-Based Virtual Machine (VM)
This specification is intended to guide a Language Model (LM) in generating executable plans that are compatible with a custom Stack-Based Virtual Machine (VM). The VM executes instructions in a specific format, manages variables, and handles dependencies between steps. By following this specification, the LM can produce plans that the VM can parse and execute to achieve various goals.

Table of Contents
Overview of the Stack-Based VM
Instruction Format
Supported Instructions
1. assign
2. llm_generate
3. retrieve_knowledge_graph
4. retrieve_knowledge_embedded_chunks
5. condition
6. reasoning
Parameters and Variable References
Variables and Dependencies
Plan Structure
Best Practices
Example Plan
Error Handling and Adjustments
Overview of the Stack-Based VM
The Stack-Based VM executes plans consisting of a sequence of instructions. Each instruction performs a specific operation and may interact with variables stored in a variable store. The VM supports conditional execution and can handle dependencies between instructions through variable assignments and references.

Key features:

Variable Store: A key-value store where variables are stored and accessed by name.
Instruction Execution: Instructions are executed sequentially unless control flow is altered by conditional statements.
Plan Parsing: Plans are provided in JSON format and parsed by the VM.
Error Handling: The VM logs errors and can adjust plans based on execution failures.
Instruction Format
Each instruction in the plan is represented as a JSON object with the following keys:

type: A string indicating the instruction type.
parameters: An object containing parameters required by the instruction.
json
Copy code
{
  "type": "instruction_type",
  "parameters": {
    "param1": "value_or_variable_reference",
    "param2": "value_or_variable_reference",
    "...": "..."
  }
}
Supported Instructions
1. assign
Purpose: Assigns a value to a variable.

Parameters:

value: The value to assign. Can be a direct value or a variable reference.
var_name: The name of the variable to assign the value to.
Example:

json
Copy code
{
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

json
Copy code
{
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

json
Copy code
{
  "type": "retrieve_knowledge_graph",
  "parameters": {
    "query": "Tallest mountain in the world",
    "output_var": "knowledge_data"
  }
}
4. retrieve_knowledge_embedded_chunks
Purpose: Retrieves embedded knowledge chunks based on an embedding query.

Parameters:

embedding_query: The embedding query string. Can be a direct string or a variable reference.
top_k: The number of top chunks to retrieve. Can be a direct integer or a variable reference.
output_var: The name of the variable to store the retrieved chunks.
Example:

json
Copy code
{
  "type": "retrieve_knowledge_embedded_chunks",
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

json
Copy code
{
  "type": "condition",
  "parameters": {
    "prompt": "Is {{number}} even? Respond with 'true' or 'false'.",
    "context": null,
    "true_branch": [
      {
        "type": "assign",
        "parameters": {
          "value": "The number is even.",
          "var_name": "result"
        }
      }
    ],
    "false_branch": [
      {
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
Purpose: Provides a detailed explanation of the plan's reasoning, analysis, and steps.

Parameters:

explanation: A string containing the reasoning and analysis for the plan.
dependency_analysis: A string or structured data describing the dependencies between different steps or sub-queries in the plan.

Example:

json
Copy code
{
  "type": "reasoning",
  "parameters": {
    "explanation": "To determine the population of the capital city of the third largest neighboring country of France by area, we will follow these steps:\n1. Retrieve a list of France's neighboring countries sorted by area.\n2. Identify the third largest country from this list.\n3. Find the capital city of the identified country.\n4. Retrieve population data for the capital city.\n5. Extract and validate the population number.\n6. Format the final answer.",
    "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2.\nStep 4 depends on Step 3.\nStep 5 depends on Step 4.\nStep 6 depends on Step 5."
  }
}
Parameters and Variable References
Parameters can be either direct values or variable references. To reference a variable, use a dictionary with the key "var" and the variable name as the value.

Direct Value Example:

json
Copy code
"prompt": "What is the capital of France?"
Variable Reference Example:

json
Copy code
"prompt": { "var": "user_question" }
When the VM encounters a variable reference, it will replace it with the value stored in the variable store under that name.

Variables and Dependencies
Variable Assignment: Use the assign instruction or specify an output_var in instructions that produce outputs.
Variable Access: Reference variables in parameters using the variable reference format.
Dependencies: Manage dependencies by assigning outputs to variables and referencing them in subsequent instructions.
Plan Structure
Sequential Execution: Instructions are executed in order unless altered by control flow instructions like condition.
Control Flow: Use the condition instruction for branching logic.
Subplans: Branches in a condition instruction are subplans (lists of instructions).
Best Practices
Variable Naming: Use descriptive variable names to make the plan readable and maintainable.
Error Handling: Anticipate possible failures and structure the plan to handle them gracefully.
Contextual Prompts: Provide sufficient context to the LLM in prompts to ensure accurate responses.
Consistency: Maintain a consistent structure and format throughout the plan.
Testing: Verify the plan for syntax correctness and logical flow before execution.
Example Plan
Goal: Determine the population of the capital city of the third largest neighboring country of France by area.

The plan:
[
  {
    "type": "reasoning",
    "parameters": {
      "explanation": "To determine the population of the capital city of the third largest neighboring country of France by area, we will follow these steps:\n1. Retrieve a list of France's neighboring countries sorted by area.\n2. Identify the third largest country from this list.\n3. Find the capital city of the identified country.\n4. Retrieve population data for the capital city.\n5. Extract and validate the population number.\n6. Format the final answer."
    }
  },
  {
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "Countries neighboring France sorted by area in descending order",
      "output_var": "france_neighbors"
    }
  },
  {
    "type": "llm_generate",
    "parameters": {
      "prompt": "Given this list of France's neighboring countries sorted by area: {{france_neighbors}}, what is the name of the third largest country?",
      "context": null,
      "output_var": "third_largest_country"
    }
  },
  {
    "type": "retrieve_knowledge_graph",
    "parameters": {
      "query": "Capital city of {{third_largest_country}}",
      "output_var": "capital_city"
    }
  },
  {
    "type": "retrieve_knowledge_embedded_chunks",
    "parameters": {
      "embedding_query": "Population of {{capital_city}}",
      "top_k": 3,
      "output_var": "population_data"
    }
  },
  {
    "type": "llm_generate",
    "parameters": {
      "prompt": "Based on this information: {{population_data}}, what is the current population of {{capital_city}}? Provide only the number.",
      "context": null,
      "output_var": "population_number"
    }
  },
  {
    "type": "condition",
    "parameters": {
      "prompt": "Is {{population_number}} a valid number? Respond with 'true' or 'false'.",
      "context": null,
      "true_branch": [
        {
          "type": "assign",
          "parameters": {
            "value": "The population of {{capital_city}}, the capital of {{third_largest_country}} (the third largest neighboring country of France by area), is {{population_number}}.",
            "var_name": "final_answer"
          }
        }
      ],
      "false_branch": [
        {
          "type": "llm_generate",
          "parameters": {
            "prompt": "The population number {{population_number}} seems invalid. Please provide a reasonable estimate for the population of {{capital_city}}, the capital of {{third_largest_country}}.",
            "context": null,
            "output_var": "estimated_population"
          }
        },
        {
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
Error Handling and Adjustments
If an instruction fails (e.g., due to invalid parameters or runtime errors), the VM logs the error.
The VM may attempt to adjust the plan based on the errors by requesting a new plan from the LLM.
To assist in adjustments, ensure that error messages are informative and that the plan is structured to allow for retries or alternative strategies.

