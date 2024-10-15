# Tool calling Instructions

Below are the instructions for calling the tools.

## llm_generate
- **Purpose**: Generates a response using the Language Model (LLM).
- **Parameters**: 
  - `prompt`: The prompt to provide to the LLM. Can be a direct string or a variable reference.
  - `context` (optional): Additional context for the LLM. Can be a direct string or a variable reference.
- **Output**:
  - If output_vars is a string: The entire LLM-generated response (whether text or JSON) will be stored under the specified variable name.
  - If output_vars is an array: It specifies that the LLM-generated response must be a valid JSON object and contain specific keys. Each entry in the array corresponds to a key in the JSON response, and the value associated with each key will be extracted and stored as a variable.

**Example:**
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool": "llm_generate", 
    "params": {
      "prompt": "Simulate the step-by-step execution of the following Python code to count the occurrences of the character 'r' in the word 'strawberry'. Provide a detailed explanation of each step and the final numerical result.\n\nword = 'strawberry'\ncount = 0\nfor char in word:\n    if char == 'r':\n        count += 1\nprint(count)\n\n Example output:To count the occurrences of the character 'r' in the word 'strawberry' using the provided pseudo Python code, we can break it down step by step:\n\n1. Initialization:\n   - Set word = 'strawberry' and char_to_count = 'r'.\n\n2. Convert to Lowercase:\n   - Both word and char_to_count are already in lowercase:\n     word = 'strawberry'\n     char_to_count = 'r'\n\n3. Count Occurrences:\n   We iterate through each character c in word and check if c is equal to char_to_count ('r'):\n   - 's' → not 'r' (count = 0)\n   - 't' → not 'r' (count = 0)\n   - 'r' → is 'r' (count = 1)\n   - 'a' → not 'r' (count = 1)\n   - 'w' → not 'r' (count = 1)\n   - 'b' → not 'r' (count = 1)\n   - 'e' → not 'r' (count = 1)\n   - 'r' → is 'r' (count = 2)\n   - 'r' → is 'r' (count = 3)\n   - 'y' → not 'r' (count = 3)\n\n4. Final Count:\n   The total count of 'r' in 'strawberry' is 3.\n\nThus, the numerical result is 3.",
      "context": null
    },
    "output_vars": "r_count_by_pseudo_python_simulation"
  }
}
```

Example with json response:
```json
{
  "seq_no": 1,
  "type": "calling",
  "parameters": {
    "tool": "llm_generate",
    "params": {
      "prompt": "Analyze the sales data and provide summary and insights.",
      "context": "${sales_data}",
    },
    "output_vars": ["summary", "insights"]
  }
}
```

## retrieve_knowledge_graph
- **Purpose**: Retrieves information from a knowledge graph based on a query, returning nodes and relationships between those nodes.
- **Parameters**:
  - `query`: The query string. Can be a direct string or a variable reference.
- **Output**: output_var is a string that contains the entire response from the knowledge graph.

**Example:**
```json
{
  "seq_no": 2,
  "type": "calling",
  "parameters": {
    "tool": "retrieve_knowledge_graph",
    "params": {
      "query": "TiDB latest stable version"
    },
    "output_vars": "tidb_version_graph"
  }
}
```

## vector_search
- **Purpose**: Retrieves embedded knowledge chunks based on an embedding query.
- **Parameters**:
  - `query`: The query string. Can be a direct string or a variable reference.
  - `top_k`: The number of top chunks to retrieve. Can be a direct integer or a variable reference.
- **Output**: output_var is a string that contains the entire response from the vector search.

**Example:**
```json
{
  "seq_no": 3,
  "type": "calling",
  "parameters": {
    "tool": "vector_search",
    "params": {
      "query": "Information about Mount Everest",
      "top_k": 3
    },
    "output_vars": "embedded_chunks"
  } 
}
```