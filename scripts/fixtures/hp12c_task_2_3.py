"""Repository-owned acceptance fixture for HP12C memory registers."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


INDEX_HTML = Path(__file__).parents[1] / "app" / "index.html"


def _evaluate_product(js_code: str) -> None:
    node_script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const html = fs.readFileSync({str(INDEX_HTML)!r}, 'utf8');
        const scripts = [...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)]
          .map((match) => match[1])
          .filter((source) => source.includes('class RPNStack'));
        if (!scripts.length) throw new Error('app/index.html must expose RPNStack');
        const document = {{
          querySelector() {{ return null; }},
          querySelectorAll() {{ return []; }},
          addEventListener() {{}},
          getElementById() {{
            return {{ value: '', textContent: '0', style: {{}}, addEventListener() {{}} }};
          }}
        }};
        const sandbox = {{ document, window: {{}}, console }};
        vm.createContext(sandbox);
        for (const source of scripts) vm.runInContext(source, sandbox, {{ filename: 'app/index.html' }});
        {js_code}
        """
    )
    result = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        cwd=str(INDEX_HTML.parents[1]),
        timeout=10,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"Node acceptance failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def test_memory_registers_and_arithmetic_store_are_product_behaviors() -> None:
    _evaluate_product(
        r"""
        const Stack = sandbox.window.RPNStack || sandbox.RPNStack;
        if (typeof Stack !== 'function') throw new Error('RPNStack is required');
        const assert = (condition, message) => { if (!condition) throw new Error(message); };
        const exercise = (operation, expected) => {
          const stack = new Stack();
          for (let register = 0; register < 10; register++) {
            stack.enter(register * 10);
            stack.sto(register);
            stack.clx();
            stack.rcl(register);
            assert(stack.X === register * 10, `RCL ${register} returned ${stack.X}`);
          }
          stack.enter(10);
          stack.sto(0);
          stack.clx();
          stack.enter(5);
          stack[operation](0);
          stack.rcl(0);
          assert(stack.X === expected, `${operation} expected ${expected}, got ${stack.X}`);
        };
        exercise('sto_plus', 15);
        exercise('sto_minus', 5);
        exercise('sto_multiply', 50);
        exercise('sto_divide', 2);
        """
    )
