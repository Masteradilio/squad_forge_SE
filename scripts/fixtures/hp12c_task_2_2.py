"""Repository-owned acceptance fixture for the HP12C ALG mode task."""

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
        const htmlPath = {str(INDEX_HTML)!r};
        const html = fs.readFileSync(htmlPath, 'utf8');
        const scripts = [...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)];
        if (!scripts.length) throw new Error('No executable script found in app/index.html');
        const productScripts = scripts.map((script) => script[1])
          .filter((source) => source.includes('class RPNStack'));
        if (!productScripts.length) throw new Error('app/index.html must expose RPNStack');
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
        for (const script of productScripts) {{
          vm.runInContext(script, sandbox, {{ filename: 'app/index.html' }});
        }}
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


def test_alg_mode_preserves_rpn_and_honors_precedence() -> None:
    """Verify the real product exposes a bounded ALG/RPN public surface."""
    _evaluate_product(
        r"""
        const Stack = sandbox.window.RPNStack || sandbox.RPNStack;
        if (typeof Stack !== 'function') throw new Error('RPNStack is required');
        const stack = new Stack();
        const assert = (condition, message) => {
          if (!condition) throw new Error(message);
        };
        assert(stack.mode === 'RPN', 'RPN must be the default mode');
        assert(typeof stack.setMode === 'function', 'setMode(mode) is required');
        assert(typeof stack.evaluateExpression === 'function', 'evaluateExpression() is required');
        stack.setMode('ALG');
        assert(stack.mode === 'ALG', 'g ALG must select ALG mode');
        assert(stack.evaluateExpression('2 + 3 * 4') === 14, 'ALG must honor precedence');
        assert(stack.evaluateExpression('(2 + 3) * 4') === 20, 'ALG must honor parentheses');
        stack.setMode('RPN');
        assert(stack.mode === 'RPN', 'g RPN must restore RPN mode');
        stack.enter(5);
        stack.enter(3);
        assert(JSON.stringify([stack.X, stack.Y, stack.Z, stack.T]) === '[3,5,0,0]',
          'ALG work must preserve RPN stack behavior');
        """
    )
