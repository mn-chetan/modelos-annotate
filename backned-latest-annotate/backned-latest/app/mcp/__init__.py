"""Model Context Protocol (MCP) capability layer.

This package is an additive, in-process wrapper around the existing
inference registry and services (vision models, annotation persistence,
dataset/ontology reads). It introduces no new model logic, no new
database schema, and no change to existing API routes; it only
standardizes how the Vision Orchestrator (``app.jobs.worker``) invokes
those capabilities so calls are structured, logged, and fail safely.
"""
