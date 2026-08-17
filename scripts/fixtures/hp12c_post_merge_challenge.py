"""Post-merge HP12C challenge for the Tester and SecurityAuditor roles.

The fixture checks the real product bundle in ``app/index.html``.  It does not
reimplement the calculator; it requires the product to expose a small,
documented challenge surface so the release agents can exercise the ten
hardest financial operations independently of the model's own unit tests.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

def _resolve_index_html() -> Path:
    candidates = [
        Path(__file__).resolve().parents[1] / "app" / "index.html",
        Path.cwd() / "app" / "index.html",
        Path(__file__).resolve().parents[2] / "app" / "index.html",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


INDEX_HTML = _resolve_index_html()


def _evaluate_product(js_code: str) -> None:
    node_script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const htmlPath = {str(INDEX_HTML)!r};
        const html = fs.readFileSync(htmlPath, 'utf8');
        const scripts = [...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)]
          .map((match) => match[1]);
        if (!scripts.length) throw new Error('app/index.html must contain executable JavaScript');
        const listeners = {{}};
        const document = {{
          body: {{ appendChild() {{}} }},
          addEventListener() {{}},
          querySelector() {{ return null; }},
          querySelectorAll() {{ return []; }},
          createElement(tag) {{
            return {{
              tagName: String(tag).toUpperCase(),
              className: '',
              innerHTML: '',
              textContent: '',
              dataset: {{}},
              style: {{}},
              addEventListener() {{}},
              appendChild() {{}},
              setAttribute() {{}},
              getAttribute() {{ return null; }},
            }};
          }},
          getElementById(id) {{
            return {{
                  id,
                  value: '',
                  textContent: '0',
                  innerHTML: '',
                  children: [{{ textContent: '' }}, {{ textContent: '' }}, {{ textContent: '' }}],
                  style: {{}},
              classList: {{ add() {{}}, remove() {{}}, toggle() {{}} }},
              appendChild() {{}},
              addEventListener(type, callback) {{
                (listeners[id] ||= {{}})[type] = callback;
              }}
            }};
          }}
        }};
        const sandbox = {{ document, window: {{}}, console, setTimeout, clearTimeout }};
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
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"HP12C post-merge challenge failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def test_complex_ten_financial_functions() -> None:
    """Exercise the ten highest-risk financial functions as one release challenge."""
    _evaluate_product(
        r"""
        const api = sandbox.window.HP12CChallenge || sandbox.HP12CChallenge;
        if (!api || typeof api !== 'object') {
          throw new Error('Expose window.HP12CChallenge for the post-merge challenge');
        }
        const assert = (condition, message) => { if (!condition) throw new Error(message); };
        const close = (actual, expected, tolerance, name) => {
          const number = Number(actual);
          assert(Number.isFinite(number), `${name} must return a finite number`);
          assert(Math.abs(number - expected) <= tolerance,
            `${name} expected ${expected}, received ${number}`);
        };
        const finiteFields = (value, fields, name) => {
          assert(value && typeof value === 'object', `${name} must return an object`);
          for (const field of fields) {
            assert(Number.isFinite(Number(value[field])), `${name}.${field} must be finite`);
          }
        };

        // 1. TVM FV: 10 periods, 5% per period, -100 payment, END timing.
        close(api.tvm({ n: 10, i: 5, pv: 0, pmt: -100, fv: 0, timing: 'END', solve: 'FV' }),
          1257.789253, 0.05, 'TVM');
        // 2. Net present value of [-100, 60, 60] at 10%.
        close(api.npv(0.10, [-100, 60, 60]), 4.132231, 0.01, 'NPV');
        // 3. Internal rate of return for the same cash flow.
        close(api.irr([-100, 60, 60]), 0.130662, 0.001, 'IRR');
        // 4. Amortization must expose a real principal/interest/balance split.
        finiteFields(api.amortization({ pv: 10000, i: 1, pmt: -888.49, periods: 1 }),
          ['principal', 'interest', 'balance'], 'AMORT');
        // 5-7. Depreciation methods for the first year of a 5-year asset.
        close(api.depreciationSL(10000, 1000, 5, 1), 1800, 0.01, 'SL');
        close(api.depreciationSOYD(10000, 1000, 5, 1), 3000, 0.01, 'SOYD');
        close(api.depreciationDB(10000, 1000, 5, 1), 4000, 0.01, 'DB');
        // 8-9. Bond price/yield round trip at 5% coupon and 6% market yield.
        close(api.bondPrice(1000, 5, 6, 10), 926.399, 0.2, 'PRICE');
        close(api.bondYield(926.399, 1000, 5, 10), 6, 0.05, 'YTM');
        // 10. Calendar difference in M.DY mode.
        close(api.dateDifference('01/01/2024', '01/31/2024', 'M.DY'), 30, 0.01, 'DATE');
        console.log('HP12C_COMPLEX_10_PASS');
        """
    )


def test_security_and_visual_contract() -> None:
    """Check the standalone bundle for obvious secret/remote-script regressions."""
    _evaluate_product(
        r"""
        const bundleHtml = fs.readFileSync(htmlPath, 'utf8');
        const assert = (condition, message) => { if (!condition) throw new Error(message); };
        assert(!/\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{16,}\b/i.test(bundleHtml),
          'bundle contains a credential-shaped token');
        assert(!/<script[^>]+src=["']https?:\/\//i.test(bundleHtml),
          'standalone bundle must not load remote scripts');
            assert(!/javascript:/i.test(bundleHtml), 'javascript URLs are not allowed');
            assert(!/\beval\s*\(|new\s+Function\s*\(/.test(bundleHtml),
              'dynamic code evaluation is not allowed in the release bundle');
            assert(/\.(?:keys|key-grid)\s*\{[^}]*grid-template-columns:\s*repeat\(\s*10\s*,/s.test(bundleHtml),
              'HP12C keypad must preserve the reference 10-column geometry');
            assert(/\.legend-top\s*\{[^}]*color:\s*#fff/i.test(bundleHtml),
              'white primary legends must be styled inside the key');
            assert(/\.legend-blue\s*\{[^}]*color:\s*#[0-9a-f]{3,6}/i.test(bundleHtml),
              'blue secondary legends must be styled inside the key');
            assert(/\.legend-orange\s*\{[^}]*position:\s*absolute[^}]*top:\s*-\d+px/s.test(bundleHtml),
              'orange legends must be positioned above the key');
            for (const label of ['AMORT', 'NPV', 'IRR', 'PRICE', 'YTM', 'SL', 'SOYD', 'DB', 'DATE']) {
              assert(bundleHtml.includes(label), `visual keypad legend is missing: ${label}`);
              const orange = new RegExp(
                `<span[^>]+class=["'][^"']*legend-orange[^"']*["'][^>]*>${label}<\\/span>`,
                'i',
              );
              const generated = new RegExp(`['"]${label}['"]`, 'i');
              assert(orange.test(bundleHtml) || generated.test(bundleHtml),
                `orange legend is missing from the keypad: ${label}`);
            }
        console.log('HP12C_SECURITY_VISUAL_PASS');
        """
    )
