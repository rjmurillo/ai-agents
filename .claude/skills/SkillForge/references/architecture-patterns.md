
Select based on task complexity:

| Pattern | Use When | Structure |
|---------|----------|-----------|
| **Single-Phase** | Simple linear tasks | Steps 1-2-3 |
| **Checklist** | Quality/compliance audits | ☐ Item verification |
| **Generator** | Creating artifacts | Input → Transform → Output |
| **Multi-Phase** | Complex ordered workflows | Phase 1 → Phase 2 → Phase 3 |
| **Multi-Agent Parallel** | Independent subtasks | Launch agents concurrently |
| **Multi-Agent Sequential** | Dependent subtasks | Agent 1 → Agent 2 → Agent 3 |
| **Orchestrator** | Coordinating multiple skills | Meta-skill chains |

### Selection Decision Tree

```
Is it a simple procedure?
├── Yes → Single-Phase
└── No → Does it produce artifacts?
    ├── Yes → Generator
    └── No → Does it verify/audit?
        ├── Yes → Checklist
        └── No → Are subtasks independent?
            ├── Yes → Multi-Agent Parallel
            └── No → Multi-Agent Sequential or Multi-Phase
```
