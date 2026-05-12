# AutoGit

> **Simplifying Git, Amplifying Productivity**

AutoGit is an AI-powered Visual Studio Code extension that automates Git workflows through a multi-agent LLM system — letting developers stay focused on code, not version control overhead.

---

## Features

| Feature | Description |
|---|---|
| **AI Commit Messages** | Generates context-aware commit messages from staged diffs using fine-tuned LLaMA 3 and Deepseek r1 models |
| **Merge Conflict Resolution** | Analyzes conflicting changes and suggests resolutions with plain-language explanations |
| **Pre-Push Testing** | Runs unit tests and static analysis in a sandboxed environment before every push |
| **Semantic Version Graph** | Stores commits, files, and feature relationships in Neo4j for rich traceability beyond linear history |
| **Documentation Generation** | Auto-generates changelogs and release notes from semantic graph data and code changes |
| **Context-Aware Assistant** | Uses RAG (LangChain + Graphiti) to maintain project history and improve AI output quality over time |

---

## Tech Stack

- **Extension:** TypeScript (VS Code API)
- **Backend:** Python, Flask
- **AI Models:** LLaMA 3, Grok — fine-tuned on CommitPackFT, ConGra, Mestre, and Zenodo datasets
- **Frameworks:** LangChain, Graphiti
- **Databases:** MongoDB (sessions & user data), Neo4j (semantic version graph)

---

## Getting Started

### Prerequisites

- Visual Studio Code
- Git
- Python 3.8+
- Node.js
- Running instances of MongoDB and Neo4j

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/AutoGit.git

# 2. Install backend dependencies
cd AutoGit/backend
pip install -r requirements.txt

# 3. Install extension dependencies
cd ../vscode-extension
npm install
```

4. Add your MongoDB and Neo4j connection strings to the backend configuration file.
5. Launch the extension in VS Code debug mode (`F5`) or package it locally with `vsce package`.

---

## Performance

- **82%** reduction in time spent writing commit messages vs. manual methods
- **4.3 / 5.0** average developer satisfaction score for generated commit quality
- **~2–2.5s** average response time under concurrent AI requests

---

## Acknowledgements

Developed at the **Department of Computer Science, University of Engineering and Technology, Lahore**, under the supervision of **Dr. Aatif**.

Built with LLaMA 3, LangChain, Neo4j, and MongoDB. Trained on the CommitPackFT, Zenodo merge conflict, and Mestre datasets.

---

## License

For licensing information, please contact the Department of Computer Science, UET Lahore.
