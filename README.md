# LOCAL Agent Kit for LINE

> A LINE × Google AI local-service agent project.

[繁體中文](README.zh-TW.md)

**Author:** Jia-Sin Chen（陳佳新／佳新哥） · GitHub: `jarsing`  
**Series:** LOCAL：30 天打造 LINE × Google AI 地方服務 Agent

## Status: Day 1 design checkpoint

This repository begins with documentation and a synthetic acceptance specification. A working agent, cloud deployment, and measured evaluation results are not available in this checkpoint.

The planned writing period is September 15–October 14, 2026. GitHub commits do not establish iThome publication or daily participation counts.

## What LOCAL means

LOCAL is the project brand, written in uppercase without periods. Its five letters also describe five design concerns:

- **L — LINE-native Interface:** the user-facing service entry point.
- **O — Orchestration & Tools:** controlled tool requests and execution.
- **C — Context & Consented Memory:** conversation, task state, and consented memory.
- **A — Assurance & Accountability:** evaluation, authorization, and human responsibility.
- **L — Launch & Learning Loop:** deployment, observation, and improvement.

These are design concerns, not five separate products or a fixed runtime sequence.

## Why this project?

Changhua, Taiwan is the first reference setting. LOCAL aims to help developers connect Google AI to LINE-based local services and later replace the data and tools for another domain.

**AI saying “done” is not proof that the backend task was completed.**

Gemini API, Google AI Studio, Google ADK, Google Antigravity, and Google Cloud are planned parts of the implementation and development workflow. Their actual roles and versions will be documented as they are tested.

## Day 1 specification

File: `docs/day01/handoff-timeout-001.json`

This synthetic case describes a confirmed handoff request whose tool call times out while the backend state remains unknown. It is not an official API payload or an executed integration test.

## Data and licensing

Use synthetic or explicitly authorized data. Never publish client code, real LINE user IDs, credentials, or private operational data.

An open-source release is planned. No license has yet been selected for this design snapshot; public visibility alone is not an open-source license. Code, articles, illustrations, and data will have their licensing scope clarified before reuse is offered.
