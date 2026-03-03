# Security Policy

## Supported Versions

Currently, the master branch and all tagged releases >= `v1.0` receive security updates.

| Version | Supported          |
| ------- | ------------------ |
| >= 1.0  | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of the Antigravity 3-Tier Multi-Agent Architecture very seriously. If you discover a security vulnerability within this project, please DO NOT open a public issue.

Instead, please send an e-mail to the repository maintainers outlining the vulnerability and steps to reproduce.

We will endeavor to respond to all reports within 48 hours and patch confirmed vulnerabilities within 7 days. You will be credited (if desired) in any resulting security advisories.

## Prompt Injection Defenses
As of v1.2, basic input sanitization is active on the orchestrator's `reconstruct_prompt` entrypoint to filter basic system-override commands. However, users are strongly advised to run untrusted input in heavily sandboxed or containerized environments.
