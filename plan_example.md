**Goal**: Provide best practices for optimizing TiDB performance for a high-volume e-commerce application, considering the latest stable version of TiDB.

**The plan:**
```json
[
  {
    "parameters": {
      "chain_of_thoughts": "Problem Essence:\n  - Core: Performance optimization for high-concurrency e-commerce workloads\n  - Assumptions: Using latest stable TiDB version\n  - Archetype: Version-specific configuration optimization\n\nTechnical Blueprint:\n■ Version Establishment\n  → KG Query: 'TiDB latest stable release'\n■ Schema Optimization\n  → Vector: 'TiDB e-commerce schema design'\n■ Transaction Handling\n  → Vector: 'distributed transaction patterns'\n■ Monitoring Configuration\n  → KG: 'Performance monitoring parameters'\n\nExecution Map:\nValidate Version → Load Config Presets → Analyze Workload Patterns → Generate Recommendations\n\n! Risk: Validate async_commit compatibility with application requirements",
      "dependency_analysis": "Step1 → Step2 → [Step3|Step4] → Step5 → [Step6|Step7] → Step8 → [Step9|Step10] → Step11 → Step12 → Step13"
    },
    "seq_no": 0,
    "type": "reasoning"
  },
  {
    "parameters": {
      "output_vars": [
        "version_info"
      ],
      "tool_name": "retrieve_knowledge_graph",
      "tool_params": {
        "query": "TiDB latest stable version release information"
      }
    },
    "seq_no": 1,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "tidb_version",
        "release_date"
      ],
      "tool_name": "llm_generate",
      "tool_params": {
        "context": null,
        "prompt": "Extract the latest stable TiDB version number from the knowledge graph data in ${version_info}. Respond with JSON: {\"version\": \"x.y.z\", \"release_date\": \"YYYY-MM-DD\"}\n\nPlease ensure that the generated text uses English."
      }
    },
    "seq_no": 2,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "general_optimizations_kg"
      ],
      "tool_name": "retrieve_knowledge_graph",
      "tool_params": {
        "query": "TiDB ${tidb_version} performance optimization best practices for e-commerce"
      }
    },
    "seq_no": 3,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "general_optimizations_chunks"
      ],
      "tool_name": "vector_search",
      "tool_params": {
        "query": "TiDB ${tidb_version} performance optimization best practices for e-commerce",
        "top_k": 10
      }
    },
    "seq_no": 4,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "general_optimizations"
      ],
      "tool_name": "llm_generate",
      "tool_params": {
        "context": "the retrieved knowledge graph data:\n${general_optimizations_kg}\n\n the retrieved chunks:\n${general_optimizations_chunks}",
        "prompt": "Extract the general optimization best practices for e-commerce from the knowledge graph data and chunks. Please include source citations from chunks source_uri."
      }
    },
    "seq_no": 5,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "transaction_patterns_kg"
      ],
      "tool_name": "retrieve_knowledge_graph",
      "tool_params": {
        "query": "High-volume transaction patterns in TiDB e-commerce applications"
      }
    },
    "seq_no": 6,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "transaction_patterns_chunks"
      ],
      "tool_name": "vector_search",
      "tool_params": {
        "query": "High-volume transaction patterns in TiDB e-commerce applications",
        "top_k": 5
      }
    },
    "seq_no": 7,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "transaction_patterns"
      ],
      "tool_name": "llm_generate",
      "tool_params": {
        "context": "the retrieved knowledge graph data:\n${transaction_patterns_kg}\n\n the retrieved chunks:\n${transaction_patterns_chunks}",
        "prompt": "Extract the TiDB transaction patterns for high-volume e-commerce applications from the knowledge graph data and chunks. Please include source citations from chunks source_uri."
      }
    },
    "seq_no": 8,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "config_parameters_kg"
      ],
      "tool_name": "retrieve_knowledge_graph",
      "tool_params": {
        "query": "TiDB ${tidb_version} configuration parameters for high concurrency"
      }
    },
    "seq_no": 9,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "config_parameters_chunks"
      ],
      "tool_name": "vector_search",
      "tool_params": {
        "query": "TiDB ${tidb_version} configuration parameters for high concurrency",
        "top_k": 5
      }
    },
    "seq_no": 10,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "config_parameters"
      ],
      "tool_name": "llm_generate",
      "tool_params": {
        "context": "the retrieved knowledge graph data:\n${config_parameters_kg}\n\n the retrieved chunks:\n${config_parameters_chunks}",
        "prompt": "Extract the TiDB configuration parameters for high concurrency from the knowledge graph data and chunks. Please include source citations from chunks source_uri."
      }
    },
    "seq_no": 11,
    "type": "calling"
  },
  {
    "parameters": {
      "output_vars": [
        "optimization_report"
      ],
      "tool_name": "llm_generate",
      "tool_params": {
        "context": null,
        "prompt": "Synthesize comprehensive optimization recommendations from these resources:\n1. General Optimizations: ${general_optimizations}\n2. Transaction Patterns: ${transaction_patterns}\n3. Configuration: ${config_parameters}\n\nOrganize into categories: Schema Design, Indexing Strategy, Transaction Handling, Monitoring. Include specific parameter recommendations for version ${tidb_version}. Format using markdown sections.\n\nPlease ensure that the generated text uses English. Please include source citations from chunks source_uri."
      }
    },
    "seq_no": 12,
    "type": "calling"
  },
  {
    "parameters": {
      "final_answer": "TiDB ${tidb_version} Optimization Best Practices (Release Date: ${release_date})\n\n${optimization_report}"
    },
    "seq_no": 13,
    "type": "assign"
  }
]
```