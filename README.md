# Ollux

> **Ollama, but civilized.**

Ollux is a lightweight, local-first CLI interface for [Ollama](https://ollama.com/) that makes local LLMs significantly nicer to use from the terminal.

It takes output from **any Ollama model**, performs deterministic local formatting, and presents the result as clean Markdown for:

- terminal reading
- technical study
- programming
- mathematical work
- Markdown files
- Unix pipelines
- Obsidian

The central idea is simple:

```text
                    ANY OLLAMA MODEL
                           │
                           ▼
                      ┌─────────┐
                      │  Ollux  │
                      └────┬────┘
                           │
                           ▼
                    Local formatting
                           │
                           ▼
                     Clean Markdown
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           Terminal       .md        Obsidian