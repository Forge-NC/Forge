# Forge NC -- Local AI Coding Assistant

Forge NC (Neural Cortex) is a VS Code extension that brings AI-powered code
assistance to your editor, running entirely on your local machine via
[Ollama](https://ollama.com). No cloud API keys, no data leaves your workstation.

## Features

- **Inline Completions** -- context-aware code suggestions as you type, powered
  by your local GPU.
- **Chat Sidebar** -- conversational AI panel for longer questions, architecture
  discussions, and exploratory coding.
- **Explain Selection** -- highlight code and get a plain-language explanation.
- **Fix Selection** -- select broken code and receive a corrected version with
  an explanation of what was wrong.
- **Refactor Selection** -- restructure selected code for clarity, performance,
  or idiomatic style.
- **Generate Tests** -- produce unit tests for the selected function or class.
- **Forge Crucible Security** -- Forge Crucible's 9-layer threat detection runs
  in the Forge desktop app, keeping your codebase safe during AI-assisted work.

## Requirements

- [Ollama](https://ollama.com) installed and running locally (default
  `http://localhost:11434`).
- A model pulled into Ollama (e.g. `ollama pull qwen2.5-coder:14b`).
- A CUDA-capable GPU is strongly recommended for acceptable latency.

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `forge.ollamaUrl` | `http://localhost:11434` | Ollama API URL |
| `forge.model` | `qwen2.5-coder:14b` | Default model for completions and chat |
| `forge.completionModel` | *(blank -- uses main model)* | Model override for inline completions |
| `forge.completionEnabled` | `true` | Enable inline code completions |
| `forge.completionDelay` | `500` | Delay in ms before triggering a completion |
| `forge.maxCompletionTokens` | `128` | Max tokens for inline completions |
| `forge.contextLines` | `50` | Lines of context above/below cursor sent to the model |

## Getting Started

1. Install and start [Ollama](https://ollama.com).
2. Pull a coding model: `ollama pull qwen2.5-coder:14b`.
3. Install the Forge NC extension from the VS Code Marketplace.
4. Open a source file and start typing -- inline suggestions appear
   automatically. Use the activity-bar icon to open the chat panel.

## Documentation

Full documentation, release notes, and the Forge CLI are available at
[https://forge-nc.dev](https://forge-nc.dev).

## License

Proprietary. See LICENSE for details.
