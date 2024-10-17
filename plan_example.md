# Example Plan
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
         We'll first determine the latest stable version of TiDB, then gather relevant information about its features and optimization techniques, with a focus on e-commerce applications.

      2. **Key Decision Points and Rationale**:
         a. **Using both knowledge graph and vector search**: This allows us to leverage structured relationships (knowledge graph) and semantic similarity (vector search) for comprehensive information gathering.
         b. **Conditional logic for version determination**: This helps us handle cases where the exact version might not be clear from the knowledge graph data.

      3. **Assumptions**:
         - The latest stable version of TiDB is the most relevant for current optimization practices.
         - E-commerce applications have specific performance requirements that may differ from general use cases.

      4. **Alternative Approaches Considered**:
         - We could have used only vector search, but this might miss important structured relationships in the data.
         - We could have skipped version-specific information, but this would likely result in less accurate and relevant recommendations.

      5. **Expected Outcomes**:
         - **Steps 1-2**: Identification of the latest TiDB version
         - **Steps 3-6**: Gathering of version-specific and general TiDB information
         - **Steps 7-8**: Collection of performance techniques and e-commerce-specific optimizations
         - **Steps 9-10**: Synthesis of gathered information into actionable recommendations

      6. **Information Combination**:
         The LLM will synthesize the version-specific features, general performance techniques, and e-commerce considerations to create a comprehensive set of recommendations.

      7. **Limitations**:
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
      "tool": "retrieve_knowledge_graph",
      "params": {
        "query": "TiDB latest stable version"
      },
      "output_vars": "latest_tidb_version_info"
    },
    "execution_objective": "Purpose: Retrieve the latest stable version information of TiDB from the knowledge graph to ensure the plan is based on the most recent and relevant data. \nExpected Output: The output variable 'latest_tidb_version_info' will contain a complex structured object representing the knowledge graph data related to the query (e.g., including entities, relationships, and metadata). \nUsage: Since the data structure is complex, extracting specific information such as the exact version number requires further processing using the 'llm_generate' tool. In subsequent steps, 'latest_tidb_version_info' will be processed to extract the precise TiDB version number needed for fetching version-specific features and optimizations."
  },
  {
    "seq_no": 2,
    "type": "calling",
    "parameters": {
      "tool": "llm_generate",
      "params": {
        "prompt": "Analyze the provided knowledge graph data to extract the latest stable version number of TiDB and its release date.\n\n- Focus specifically on entities related to 'Release Notes'.\n- If multiple version numbers are found, select the one with the most recent release date.\n- Version numbers may be in the format 'vX.Y.Z' or 'vX.Y.Z-suffix' (e.g., 'v8.3.0-DMR').\n\n- Respond only with the latest stable version number and release date in JSON format, (e.g., {'latest_tidb_version': 'v8.1.1', 'release_date': '2024-08-27'})\n- If no specific stable version number is found, respond exactly {'latest_tidb_version': 'latest stable version tidb', 'release_date': null}.",
        "context": "the retrieved knowledge graph data:\n${latest_tidb_version_info}"
      },
      "output_vars": ["latest_tidb_version", "release_date"]
    },
    "execution_objective": "Extract the latest stable version number and its release date from the retrieved knowledge graph data to identify the target version for optimization."
  },
  {
    "seq_no": 3,
    "type": "jmp",
    "parameters": {
      "condition_prompt": "Was a specific latest stable version of TiDB found? Respond with a JSON object in the following format:\n{\n  \"result\": boolean,\n  \"explanation\": string\n}\nWhere 'result' is true if a specific version was found, false otherwise, and 'explanation' provides a brief reason for the result.",
      "context": "Latest TiDB version: ${latest_tidb_version}",
      "jump_if_true": 4,
      "jump_if_false": 6
    },
    "execution_objective": "Purpose: Assess whether a specific latest stable version of TiDB has been successfully retrieved from the knowledge graph. \n\nUsage: Based on the value of `result`, the VM will determine the next execution path:\n- If `result` is `true`: The VM will jump to sequence number **4** to gather detailed, version-specific information about TiDB.\n- If `result` is `false`: The VM will jump to sequence number **6** to utilize general TiDB data, ensuring that the plan can proceed even without specific version details."
  },
  {
    "seq_no": 4,
    "type": "calling",
    "parameters": {
      "tool": "vector_search",
      "params": {
        "query": "What are the key features and improvements in TiDB version ${latest_tidb_version}?",
        "top_k": 3
      },
      "output_vars": "tidb_info"
    },
    "execution_objective": "Purpose: Utilize the 'vector_search' tool to retrieve the top 3 documents that detail the key features and improvements of the specified TiDB version (${latest_tidb_version}). \n\nExpected Output: The output variable 'tidb_info' will contain a list of 3 document chunks related to the key features and improvements of the specified TiDB version. \n\nUsage: The retrieved information in 'tidb_info' will be used in subsequent steps (using 'llm_generate') to generate a comprehensive and detailed final answer that highlights the specific enhancements of the identified TiDB version."
  },
  {
    "seq_no": 5,
    "type": "jmp",
    "parameters": {
      "target_seq": 7
    },
    "execution_objective": "Unconditionally jump to sequence number 7 to continue with performance-specific optimization steps, bypassing steps that are not needed."
  },
  {
    "seq_no": 6,
    "type": "calling",
    "parameters": {
      "tool": "vector_search",
      "params": {
        "query": "Latest TiDB version and its key features",
        "top_k": 3
      },
      "output_vars": "tidb_info"
    },
    "execution_objective": "Purpose: Utilize the 'vector_search' tool to retrieve the top 3 documents that provide general information about the latest TiDB version and its key features when a specific version was not found. \n\nExpected Output: The output variable 'tidb_info' will contain a list of 3 document chunks related to the latest TiDB version and its key features. \n\nUsage: The retrieved general information in 'tidb_info' will be used in subsequent steps (using 'llm_generate') to generate a comprehensive final answer, ensuring that the plan can proceed with relevant data even in the absence of specific version details."
  },
  {
    "seq_no": 7,
    "type": "calling",
    "parameters": {
      "tool": "vector_search",
      "params": {
        "query": "TiDB ${latest_tidb_version} performance optimization techniques",
        "top_k": 5
      },
      "output_vars": "performance_techniques"
    },
    "execution_objective": "Purpose: Utilize the 'vector_search' tool to retrieve the top 5 documents that outline performance optimization techniques specific to the identified TiDB version (${latest_tidb_version}). \n\nUsage: The retrieved performance optimization techniques will be used in subsequent steps to formulate detailed recommendations for enhancing TiDB's performance in high-volume e-commerce environments. Additionally, if further granularity is needed, additional queries or processing steps using 'llm_generate' may be employed to extract specific strategies or best practices from the retrieved documents."
  },
  {
    "seq_no": 8,
    "type": "calling",
    "parameters": {
      "tool": "vector_search",
      "params": {
        "query": "What are specific considerations for optimizing TiDB ${latest_tidb_version} for e-commerce applications?",
        "top_k": 5
      },
      "output_vars": "ecommerce_optimizations"
    },
    "execution_objective": "Purpose: Use the 'vector_search' tool to retrieve the top 5 documents that discuss specific considerations and best practices for optimizing TiDB (${latest_tidb_version}) in the context of e-commerce applications. \n\nUsage: The information gathered in 'ecommerce_optimizations' will be integrated into the final recommendations to ensure that performance optimizations are aligned with the unique demands of high-volume e-commerce platforms. Additionally, if more detailed insights are required, subsequent steps may involve using 'llm_generate' to extract and elaborate on specific considerations from the retrieved documents."
  },
  {
    "seq_no": 9,
    "type": "calling",
    "parameters": {
      "tool": "llm_generate",
      "params": {
        "prompt": "Provide a comprehensive list of best practices for optimizing TiDB performance for a high-volume e-commerce application. Organize the recommendations into categories such as schema design, indexing, query optimization, and infrastructure scaling. Ensure that all recommendations are applicable to TiDB version ${latest_tidb_version}.",
        "context": "Based on the following information for TiDB version ${latest_tidb_version}:\n1. TiDB Overview: ${tidb_info}\n2. Performance Techniques: ${performance_techniques}\n3. E-commerce Optimizations: ${ecommerce_optimizations}"
      },
      "output_vars": "final_recommendations"
    },
    "execution_objective": "Purpose: Use the 'llm_generate' tool to synthesize the retrieved performance optimization techniques and e-commerce-specific considerations into a cohesive set of best practices for optimizing TiDB (${latest_tidb_version}) in high-volume e-commerce applications.\n\nExpected Output: The output variable 'final_recommendations' will contain a detailed and actionable list of best practices organized into relevant categories such as schema design, indexing, query optimization, and infrastructure scaling.\n\nUsage: These comprehensive recommendations will be integrated into the final answer to provide the user with a structured and thorough guide for optimizing TiDB in their specific application context."
  },
  {
    "seq_no": 10,
    "type": "assign",
    "parameters": {
      "final_answer": "Best practices for optimizing TiDB ${latest_tidb_version} (released on ${release_date}) performance for a high-volume e-commerce application:\n\n${final_recommendations}"
    }
  }
]
```