# Hermes on fnOS

Automated arm64 fnOS packaging for [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

The repository checks the latest stable upstream release every day. When a new tag appears, GitHub Actions builds a self-contained Python 3.11 + Node.js runtime, packages it as an fnOS `.fpk`, verifies the archive, and publishes a GitHub Release.

## Install

Download the latest `trim.hermes_*_arm64.fpk` from Releases and install it with fnOS App Center's local-install function. Application data lives in fnOS' package data directory and is preserved during upgrades.

## Build locally

Requirements: Linux, Docker with Buildx, `bash`, `curl`, `jq`, `tar`, and `gzip`.

```bash
./scripts/build.sh v2026.9.11
```

Artifacts are written to `dist/`.

## Packaging boundary

- Hermes itself is fetched from the requested immutable upstream tag.
- Python, Node.js, and native dependencies are assembled for Linux arm64 in Docker.
- The fnOS lifecycle scripts, UI, and gateway wrapper are separate from persisted Hermes data.
- `package/app/wrapper/trim-hermes-wrapper` is the compatibility binary recovered from the currently working fnOS package. Its source was not present in the installed package. It is tracked with a SHA-256 checksum and should eventually be replaced by a source-built implementation.

This is an unofficial community package and is not affiliated with Nous Research or fnOS.
