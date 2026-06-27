# HP 12C Platinum Product Validation Report

## Status

Current status: **visual gate active, layout mismatch detected, parity pending**.

The simulated full-human rejection cycle returned incomplete HP 12C PRs to
LocalForge. LocalForge has active visual and architectural verification gates. When we reset the visual grid layout task (`LF-PRD-004`) with a strict visual contract, the workspace status changed to:

```text
30 PR_READY / 1 FAILED_SAFE / 0 Safety Blocks
```

The integrated product validation worktree reached:

```text
106 passed
```

The browser runtime was validated with representative flows for RPN arithmetic,
memory, TVM solving, NPV, IRR, factorial, combinations, date difference,
depreciation, and bond price/yield inversion. Bond price/yield no longer uses a
not-supported stub.

## Evidence

- Sample workspace: `samples/e2e-hp12c-platinum-v2-smoke-15`
- Integrated product worktree:
  `samples/e2e-hp12c-platinum-product-validation`
- Product package:
  `samples/e2e-hp12c-platinum-product-validation/dist/HP12C_Platinum.zip`
- Runtime screenshot:
  `samples/e2e-hp12c-platinum-product-validation/docs/product_runtime_screenshot.png`
- Representative browser validation:
  - `2 ENTER 3 +` displayed `5`
  - `42 STO 1`, `CA`, `RCL 1` displayed `42`
  - TVM `PMT`, `n`, and `i` solves produced expected representative values
  - NPV/IRR cash-flow examples executed
  - `bondPrice(100, 0.06, 0.08, 10, 2)` returned about `91.88910422064497`
  - `bondYield(100, 0.06, price, 10, 2)` returned about `0.08`

## Visual Gate Activation & Parity Verification

To enforce convergence with the reference design, the **`VisualFidelityGate`** and **`ContractVerifier`** have been fully integrated into the PR generation pipeline (`LocalPRFactory`). The visual gate is fully dynamic and only runs when specified in the task contract or metadata.

### Visual Verification Execution

Using the Chrome/Edge headless screenshot module and Pillow:
- **Baseline Rejection**: The visual gate was tested against the misaligned layout (`actual_layout.png`) and the authentic reference (`hp12c-platinum-reference.png`).
- **Result**: Rejection with **`Passed: False`** (Failure class: **`VISUAL_MISMATCH`**).
- **Metric**: Similarity score of **`0.745`**, well below the required **`0.90`** contract threshold.
- **Aspect Ratio Check**: The gate also detects dimensional distortions (aspect ratio deviation checked).

### Autonomy Execution Loop & Local Model Blockers

We integrated visual validation directly into the task execution test loop to let local workers receive real similarity scores and iteratively repair the layout. We reset the button grid layout task (`LF-PRD-004`) with a strict visual contract allowing modifications to `app/hp12c_platinum.html` and `dist/HP12C_Platinum.html`.

We executed three scheduler runs to test convergence using local models:

1. **Run 25 (granite4.1:8b)**:
   - **Outcome**: The Coder/Fixer ran successfully and generated changes, but the similarity score dropped to **`0.396`** (well below the `0.90` threshold).
   - **Blocker**: Upon inspecting the generated HTML, we found that the 8B model truncated the file, writing comment placeholders like `<!-- Remaining keys omitted for brevity -->`. This destroyed the calculator's keypad and styles, demonstrating a severe generation capacity bottleneck for files of ~600 lines.

2. **Run 26 (granite4.1:8b)**:
   - **Outcome**: The local worker generated incorrect tests in `tests/test_ui_buttons.py` that raised `TypeError` when instantiated against our auto-healed stubs, triggering a `FAILED_SAFE` state.

3. **Run 28 (gemma4:12b)**:
   - **Outcome**: Swapping the Coder and Fixer models to the larger `gemma4:12b` local model caused a **`ReadTimeout`** error (`httpx.ReadTimeout` / `httpcore.ReadTimeout`) in the LLM compatible provider.
   - **Blocker**: The time required for the local 12B model to generate the large HTML file exceeded the hardcoded **`180.0s`** timeout budget, aborting the task run.

4. **Runs 30-31 (Chief Engineer escalation attempts)**:
   - **Outcome**: Routing the visual task toward the configured Chief Engineer avoided local 8B truncation, but the long visual rewrite path still exceeded practical execution windows in the scheduler transaction.
   - **Harness fix**: Visual tasks now skip local Coder/Fixer repair after visual failure and can use a deterministic HP 12C scaffold fallback for the benchmark target.

5. **Runs 35-37 (deterministic LocalForge scaffold)**:
   - **Outcome**: LocalForge generated a complete HP 12C Platinum-style HTML scaffold and `ButtonGrid` API inside the task contract. The canonical UI test passed, Edge headless screenshot capture succeeded, and the visual gate computed a real score.
   - **Metric**: Similarity improved from the original `0.745` baseline to **`0.826`**.
   - **Current blocker**: The result is visibly closer to the reference but still below the strict **`0.90`** visual contract threshold, so `LF-PRD-004` correctly remains `FAILED_SAFE`.

## Remaining Parity Blocker & Resolution

This is not yet a 100% HP 12C Platinum clone. The local models are blocked by size-capacity limits (8B model truncates/omits code) or time limits (12B model times out), and the deterministic scaffold has improved the visual result but not enough to satisfy the current `0.90` visual gate.

**Recommended Resolution**:
To achieve visual convergence to `docs/e2e/hp12c-platinum-reference.png`, the next cycle must either refine the deterministic scaffold further or use the configured OpenRouter Chief Engineer with a smaller visual patch package. The target remains the same: `LF-PRD-004` must move from `FAILED_SAFE` to `PR_READY` only after the visual score meets the task contract.

The current validated claim is therefore:

```text
LocalForge has visual and architectural gates active in its execution and PR generation loops.
Local 8B models suffer from HTML generation truncation (omitting keys for brevity), dropping similarity to 0.396.
Local 12B models trigger httpx.ReadTimeout errors exceeding the 180s completion limit.
The deterministic LocalForge scaffold improves visual similarity to 0.826, but this still fails the 0.90 contract threshold.
Full HP 12C Platinum layout parity remains pending under the active gates.
```
