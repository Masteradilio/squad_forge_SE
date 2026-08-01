"""Unit tests for SemanticCacheManager & AST Caching."""

import time
from pathlib import Path

import pytest
from localforge.services.semantic_cache import SemanticCacheManager


def test_semantic_cache_llm_hit_and_miss(tmp_path):
    cache_dir = tmp_path / "cache"
    manager = SemanticCacheManager(cache_dir=cache_dir, ttl_seconds=60)

    model = "google/gemini-2.5-flash"
    messages = [{"role": "user", "content": "Hello world"}]

    # Initially cache miss
    assert manager.get_llm_completion(model, messages) is None

    # Store response
    data = {"choices": [{"message": {"content": "Hi there!"}}]}
    manager.set_llm_completion(model, messages, data)

    # Now cache hit
    result = manager.get_llm_completion(model, messages)
    assert result is not None
    assert result["cached"] is True
    assert result["choices"][0]["message"]["content"] == "Hi there!"


def test_semantic_cache_ttl_expiry(tmp_path):
    cache_dir = tmp_path / "cache"
    manager = SemanticCacheManager(cache_dir=cache_dir, ttl_seconds=1)

    model = "groq/llama-3.3-70b"
    messages = [{"role": "user", "content": "Short test"}]
    data = {"content": "ok"}

    manager.set_llm_completion(model, messages, data)
    assert manager.get_llm_completion(model, messages) is not None

    # Wait for TTL to expire
    time.sleep(1.1)
    assert manager.get_llm_completion(model, messages) is None


def test_semantic_cache_ast_graph(tmp_path):
    cache_dir = tmp_path / "cache"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / "main.py").write_text("print('hello')", encoding="utf-8")

    manager = SemanticCacheManager(cache_dir=cache_dir)

    # Miss initially
    assert manager.get_ast_graph(ws_dir) is None

    # Save AST graph
    graph_data = {"version": "1.0.0", "nodes_count": 1}
    manager.set_ast_graph(ws_dir, graph_data)

    # Hit
    cached = manager.get_ast_graph(ws_dir)
    assert cached is not None
    assert cached["nodes_count"] == 1

    # Modify file -> Hash changes -> Cache miss
    (ws_dir / "main.py").write_text("print('updated')", encoding="utf-8")
    assert manager.get_ast_graph(ws_dir) is None
