# Changelog

All notable changes to the Forge NC extension will be documented in this file.

## 0.9.0

- Chat sidebar with persistent conversation memory across messages.
- Markdown rendering in chat responses (headings, code blocks, bold, italic, lists, links).
- Workspace context awareness: open files, visible code range, and selected code automatically included.
- FIM dual-strategy: native fill-in-middle for supported models, instruction fallback for all others.
- Clear chat button to reset conversation history.
- URL sanitization in rendered chat links for security.
- Sliding window on chat history to prevent exceeding model context window.
- Config changes to Ollama URL now take effect immediately without restart.

## 0.1.0 -- Initial Release

- Inline code completions powered by local Ollama models.
- Chat sidebar with conversational AI panel.
- Context-aware editor actions: Explain, Fix, Refactor, Generate Tests.
- Configurable model selection, completion delay, and context window size.
