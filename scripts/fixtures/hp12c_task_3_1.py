"""Repository-owned acceptance fixture for the HP12C TVM register task."""

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
        const scripts = [...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)]
          .map((match) => match[1]);
        if (!scripts.length) throw new Error('No inline executable script found');
        const document = {{
          querySelector() {{ return null; }},
          querySelectorAll() {{ return []; }},
          addEventListener() {{}},
          getElementById() {{
            return {{ value: '', textContent: '', style: {{}}, addEventListener() {{}} }};
          }}
        }};
        const sandbox = {{ document, window: {{}}, console }};
        vm.createContext(sandbox);
        for (const script of scripts) vm.runInContext(script, sandbox, {{ filename: 'app/index.html' }});
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
            f"TVM acceptance failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def test_tvm_registers_and_timing_exist() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    for register in ("n", "i", "pv", "pmt", "fv"):
        assert f'id="{register}"' in html, f"Missing input for {register}"
    assert 'id="timing"' in html
    assert "BEG" in html and "END" in html


def test_tvm_js_exports_registers_and_timing() -> None:
    _evaluate_product(
        """
        const TVM = sandbox.window.TVM || sandbox.TVM;
        if (!TVM || typeof TVM !== 'object') throw new Error('TVM object is required');
        for (const prop of ['n', 'i', 'PV', 'PMT', 'FV', 'timing']) {
          if (!(prop in TVM)) throw new Error('Missing TVM property: ' + prop);
        }
        if (typeof TVM.setReg !== 'function') throw new Error('TVM.setReg is required');
        if (typeof TVM.setTiming !== 'function') throw new Error('TVM.setTiming is required');
        TVM.setReg('n', 12);
        if (TVM.n !== 12) throw new Error('TVM n register did not update');
        TVM.setTiming('BEG');
        if (TVM.timing !== 'BEG') throw new Error('BEG timing did not update');
        TVM.setTiming('END');
        if (TVM.timing !== 'END') throw new Error('END timing did not update');
        """
    )
