# PRD: HP 12C Platinum Desktop Financial Calculator

## Product Vision
Build a standalone desktop-style web application for an authentic HP 12C Platinum financial calculator. The application must feature 100% functional button operations, RPN and Algebraic calculation modes, TVM (Time Value of Money), Cash Flow (NPV/IRR), Amortization, Depreciation, Date math, and a faithful visual design system matching the real HP 12C chassis.

---

## Epic 1: Visual Design System & Keypad Layout
- **Task 1.1**: Design the gold and dark-grey metallic chassis, LCD display screen, and status indicators (RPN, ALG, f, g, PRGM, BEGIN).
- **Task 1.2**: Implement the 4-row 10-column key grid with authentic gold (f) and blue (g) secondary legends and primary key labels.
- **Task 1.3**: Add responsive CSS styling, key press hover/active states, tactile visual feedback, and high-contrast LCD typography.

## Epic 2: Core RPN Engine & Memory Registers
- **Task 2.1**: Implement the RPN calculation stack (X, Y, Z, T registers) with stack manipulation (`ENTER`, `x≷y`, `R↓`, `CLX`).
- **Task 2.2**: Implement the Algebraic calculation mode (ALG) with operator precedence and mode toggle (`g ALG` / `g RPN`).
- **Task 2.3**: Implement memory storage and recall registers (`STO 0-9`, `RCL 0-9`, `STO +`, `STO -`, `STO *`, `STO /`).

## Epic 3: Financial & Time Value of Money (TVM) Solver
- **Task 3.1**: Implement TVM registers (`n`, `i`, `PV`, `PMT`, `FV`) and cash flow timing (`BEG` / `END`).
- **Task 3.2**: Implement TVM solver for missing variable computation (solving for `PV`, `FV`, `PMT`, `n`, `i`).
- **Task 3.3**: Implement Amortization schedule calculation (`AMORT`) for principal and interest breakdown.

## Epic 4: Cash Flow & Advanced Financial Functions
- **Task 4.1**: Implement Cash Flow entry registers (`CF0`, `CFj`, `Nj`) for irregular cash flows.
- **Task 4.2**: Implement Net Present Value (`NPV`) and Internal Rate of Return (`IRR`) solvers.
- **Task 4.3**: Implement Depreciation calculation methods (`SL`, `SOYD`, `DB`).
- **Task 4.4**: Implement Bond Price and Yield to Maturity (`PRICE`, `YTM`) financial calculations.

## Epic 5: Mathematical, Statistical & Date Functions
- **Task 5.1**: Implement standard arithmetic, percent calculations (`%`, `Δ%`, `%T`), reciprocal (`1/x`), square root (`√x`), power (`y^x`), natural log (`LN`), and exponential (`e^x`).
- **Task 5.2**: Implement 2-variable statistics (`Σ+`, `Σ-`, mean `x̄`, weighted mean `x̄w`, standard deviation `s`, linear estimation `ŷ, r`).
- **Task 5.3**: Implement calendar date math (`DATE`, `ΔDYS`) supporting M.DY and D.MY date formats.

## Epic 6: Keyboard Navigation & Product Packaging
- **Task 6.1**: Map physical computer keyboard keys (digits, operators, Enter, Backspace, Escape, f/g keys) to calculator buttons.
- **Task 6.2**: Package standalone single-page HTML bundle with unit test suite verifying all button functions.
