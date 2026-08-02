"""Adapters to the backing services the app talks to at runtime.

Database engine/session, Redis client, Kafka producer — the plumbing the domain
modules under ``src/modules/`` depend on to reach the outside world. Each new
external system the app integrates with gets its adapter here, so the domain
code never holds a driver or connection detail itself.

Deployment config (Dockerfiles, compose, Cloud Build) is unrelated and lives in
the repository-root ``infra/``.
"""
