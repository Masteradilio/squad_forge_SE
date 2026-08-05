"""Repository-owned acceptance fixture for the HP12C RPN stack task."""

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
        if (!productScripts.length) throw new Error('app/index.html must expose the RPNStack implementation');
        const listeners = {{}};
        const document = {{
          querySelector() {{ return null; }},
          querySelectorAll() {{ return []; }},
          addEventListener() {{}},
          getElementById(id) {{
            return {{
              id,
              value: '',
              textContent: '0',
              style: {{}},
              addEventListener(type, callback) {{
                (listeners[id] ||= {{}})[type] = callback;
              }}
            }};
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


def test_rpn_stack_operations_against_real_product() -> None:
    """Verify RPN behavior without reimplementing the production algorithm."""
    _evaluate_product(
        r"""
        const Stack = sandbox.window.RPNStack || sandbox.RPNStack;
        if (typeof Stack !== 'function') {
          throw new Error('app/index.html must expose RPNStack for acceptance');
        }
        const stack = new Stack();
        const assert = (condition, message) => {
          if (!condition) throw new Error(message);
        };
        const snapshot = () => [stack.X, stack.Y, stack.Z, stack.T];
        assert(JSON.stringify(snapshot()) === '[0,0,0,0]', 'stack must start empty');
        stack.enter(5);
        assert(JSON.stringify(snapshot()) === '[5,0,0,0]', 'ENTER must place 5 in X');
        stack.enter(3);
        assert(JSON.stringify(snapshot()) === '[3,5,0,0]', 'ENTER must lift old X');
        stack.swap();
        assert(JSON.stringify(snapshot()) === '[5,3,0,0]', 'x<->y must swap X and Y');
        stack.rollDown();
        assert(JSON.stringify(snapshot()) === '[3,0,0,5]', 'R-down must rotate the stack');
        stack.clx();
        assert(JSON.stringify(snapshot()) === '[0,0,0,5]', 'CLX must clear only X');
        """
    )
