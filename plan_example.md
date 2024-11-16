
### Bad Examples:

**Goal**: How can I perform a smooth upgrade of a TiDB cluster?

**The Wrong Plan:**
```json
[
  ...,
  {
    "seq_no": 1,
    "type": "calling",
    "parameters": {
      "tool_name": "retrieve_knowledge_graph",
      "tool_params": {
        "query": "Current version of TiDB cluster"
      },
      "output_vars": ["current_tidb_version"]
    }
  },
  {
    "seq_no": 2,
    "type": "assign",
    "parameters": {
      "target_tidb_version": "v6.5.0"
    }
  }
  ...
]
```

**Error Explanation**:

According to the Specification:

  - **Do Not Assume Specific Information**: Do not make assumptions about (or generate) specific details of the user’s environment, such as their current system configuration, current versions of tidb, current tiup version, or private data. Plans should be designed to be adaptable and not rely on presumed user-specific information.
  - **Avoid Obtain User-Specific Data with General Tools**: Do not attempt to obtain user-specific information using general tools that are not designed to access such information.

Specifically, the query "Current version of TiDB cluster" assumes and retrieves user-specific data, which should be strictly prohibited.
**Correct Approach**:

A correct approach would involve querying for general upgrade steps or best practices for a TiDB upgrade rather than querying for the specific version of the user’s TiDB cluster. For instance, the query could be updated to:

```json
[
  ...,
  {
    "tool_name": "retrieve_knowledge_graph",
    "tool_params": {
      "query": "TiDB smooth upgrade"
    },
    "output_vars": ["tidb_smooth_upgrade"]
  },
  ...
]
```

### Great Examples:

**Goal**: Provide best practices for optimizing TiDB performance for a high-volume e-commerce application, considering the latest stable version of TiDB.

**The plan:**
```json
[
  {
    "seq_no": 0,
    "type": "reasoning",
    "parameters": {
      "chain_of_thoughts": "To provide best practices for optimizing TiDB performance for a high-volume e-commerce application, we're adopting a multi-step approach:

      1. **Overall Strategy**:
         We'll follow these steps:
         1. Determine the latest stable version of TiDB
         2. Gather version-specific information
         3. Collect general TiDB information (if needed)
         4. Gather performance optimization techniques
         5. Collect e-commerce-specific optimizations
         6. Synthesize gathered information into actionable recommendations

      2. **Key Decision Points and Rationale**:
         a. **Using both knowledge graph and vector search**: This allows us to leverage structured relationships (knowledge graph) and semantic similarity (vector search) for comprehensive information gathering.
         b. **Conditional logic for version determination**: This helps us handle cases where the exact version might not be clear from the knowledge graph data.

      3. **Assumptions**:
         - The latest stable version of TiDB is the most relevant for current optimization practices.
         - E-commerce applications have specific performance requirements that may differ from general use cases.

      4. Compliance Checks:
       - ✓ No user-specific queries planned (will not attempt to detect current version/configuration)
       - ✓ All responses will maintain consistent language (English)
       - ✓ Final recommendations will be stored in final_answer
       - ✓ All variable references use correct ${var} syntax

      5. **Alternative Approaches Considered**:
         - We could have used only vector search, but this might miss important structured relationships in the data.
         - We could have skipped version-specific information, but this would likely result in less accurate and relevant recommendations.

      6. **Expected Outcomes**:
         - **Steps 1-2**: Identification of the latest TiDB version
         - **Steps 3-6**: Gathering of version-specific and general TiDB information
         - **Steps 7-8**: Collection of performance techniques and e-commerce-specific optimizations
         - **Steps 9-10**: Synthesis of gathered information into actionable recommendations

      7. **Information Combination**:
         The LLM will synthesize the version-specific features, general performance techniques, and e-commerce considerations to create a comprehensive set of recommendations.

      8. **Limitations**:
         - The accuracy of our recommendations depends on the freshness of the knowledge graph and vector database.
         - If no specific version is found, our recommendations may be more general and less tailored.

      This approach allows us to provide version-specific, relevant, and comprehensive optimization recommendations for TiDB in an e-commerce context.",
      "dependency_analysis": "Step 2 depends on Step 1.\nStep 3 depends on Step 2.\nStep 4 depends on Step 3 (if condition is true).\nStep 5 depends on Step 4 when condition is true (to skip Step 6).\nStep 6 depends on Step 3 (if condition is false).\nStep 7 depends on Step 4 or Step 6.\nStep 8 depends on Step 7.\nStep 9 depends on Step 8.\nStep 10 depends on Step 9."
    }
  },
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
  },
  {
    "seq_no": 2,
    "type": "calling",
    "parameters": {
      "tool_name": "llm_generate",
      "tool_params": {
        "prompt": "Analyze the provided knowledge graph data to extract the latest stable version number of TiDB and its release date.\n\n- Focus specifically on entities related to 'Release Notes'.\n- If multiple version numbers are found, select the one with the most recent release date.\n- Version numbers may be in the format 'vX.Y.Z' or 'vX.Y.Z-suffix' (e.g., 'v8.3.0-DMR').\n\n- Respond only in JSON format with keys [\"latest_stable_tidb_version\", \"release_date\"], (e.g., {\"latest_stable_tidb_version\"': \"v8.1.1\", \"release_date\": \"2024-08-27\"})\n- If no specific stable version number is found, respond exactly {\"latest_stable_tidb_version\": \"latest stable version tidb\", \"release_date\": null}.",
        "context": "the retrieved knowledge graph data:\n${latest_tidb_version_info}"
      },
      "output_vars": ["latest_stable_tidb_version", "release_date"]
    }
  },
  {
    "seq_no": 3,
    "type": "jmp",
    "parameters": {
      "condition_prompt": "Was a specific latest stable version of TiDB found? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if a specific version was found, false otherwise, and 'explanation' provides a brief reason for the result.",
      "context": "Latest TiDB version: ${latest_stable_tidb_version}",
      "jump_if_true": 4,
      "jump_if_false": 6
    }
  },
  {
    "seq_no": 4,
    "type": "calling",
    "parameters": {
      "tool_name": "vector_search",
      "tool_params": {
        "query": "What are the key features and improvements in TiDB version ${latest_stable_tidb_version}?",
        "top_k": 5
      },
      "output_vars": ["tidb_key_features_and_improvements"]
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
    "type": "calling",
    "parameters": {
      "tool_name": "vector_search",
      "tool_params": {
        "query": "Latest TiDB version and its key features",
        "top_k": 5
      },
      "output_vars": ["tidb_key_features_and_improvements"]
    }
  },
  {
    "seq_no": 7,
    "type": "calling",
    "parameters": {
      "tool_name": "vector_search",
      "tool_params": {
        "query": "TiDB ${latest_stable_tidb_version} performance optimization techniques",
        "top_k": 5
      },
      "output_vars": ["performance_techniques"]
    }
  },
  {
    "seq_no": 8,
    "type": "calling",
    "parameters": {
      "tool_name": "vector_search",
      "tool_params": {
        "query": "What are specific considerations for optimizing TiDB ${latest_stable_tidb_version} for e-commerce applications?",
        "top_k": 5
      },
      "output_vars": ["ecommerce_optimizations"]
    }
  },
  {
    "seq_no": 9,
    "type": "calling",
    "parameters": {
      "tool_name": "llm_generate",
      "tool_params": {
        "prompt": "Provide a comprehensive list of best practices for optimizing TiDB performance for a high-volume e-commerce application. Organize the recommendations into categories such as schema design, indexing, query optimization, and infrastructure scaling. Ensure that all recommendations are applicable to TiDB version ${latest_stable_tidb_version}, response in text.\n\nPlease ensure that the generated text uses English.",
        "context": "Based on the following information for TiDB version ${latest_stable_tidb_version}:\n1. TiDB Overview: ${tidb_key_features_and_improvements}\n2. Performance Techniques: ${performance_techniques}\n3. E-commerce Optimizations: ${ecommerce_optimizations}"
      },
      "output_vars": ["final_recommendations"]
    }
  },
  {
    "seq_no": 10,
    "type": "assign",
    "parameters": {
      "final_answer": "Best practices for optimizing TiDB ${latest_stable_tidb_version} (released on ${release_date}) performance for a high-volume e-commerce application:\n\n${final_recommendations}"
    }
  }
]

