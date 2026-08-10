# PRD: HP 12C Platinum Desktop Financial Calculator

## Product Vision
Build a standalone desktop-style web application for an authentic HP 12C Platinum financial calculator. The application must feature 100% functional button operations, RPN and Algebraic calculation modes, TVM (Time Value of Money), Cash Flow (NPV/IRR), Amortization, Depreciation, Date math, and a faithful visual design system matching the real HP 12C chassis.

---

## Epic 1: Visual Design System & Keypad Layout
- **Task 1.1**: Design the gold and dark-grey metallic chassis, LCD display screen, and status indicators (RPN, ALG, f, g, PRGM, BEGIN).
- **Task 1.2**: Implement the 4-row 10-column key grid with authentic gold (f) and blue (g) secondary legends and primary key labels.
- **Task 1.3**: Add responsive CSS styling, key press hover/active states, tactile visual feedback, and high-contrast LCD typography.

### Executable visual acceptance contract — 40 keypad positions

The final product must expose one direct 4-row x 10-column keypad matrix. The
matrix below is the authoritative visual and interaction contract. `ENTER`
occupies row 3, column 6 and spans the row-4 column-6 slot; that slot is kept
in the matrix so the contract contains all 40 visual positions while the
implementation renders one physical spanning control.

Legend rules for every position: the primary label is white and inside the
keycap; the blue legend is below the primary label and inside the keycap; the
orange legend is above the keycap and outside it. A dash means that the
position has no legend in that color. Labels, positions, and actions are
validated through the rendered interface, not through an API-only substitute.

| # | Row | Column | Primary label (white, inside) | Blue legend (inside, below) | Orange legend (above, outside) | Required interface action |
|---:|---:|---:|---|---|---|---|
| 1 | 1 | 1 | n | CFo | AMORT | Store/read the number of periods and open the amortization operation when shifted |
| 2 | 1 | 2 | i | CFj | INT | Store/read the interest rate and calculate interest when shifted |
| 3 | 1 | 3 | PV | Nj | NPV | Store/read present value and calculate net present value when shifted |
| 4 | 1 | 4 | PMT | CFj | RND | Store/read payment and round the displayed value when shifted |
| 5 | 1 | 5 | FV | Nj | IRR | Store/read future value and calculate internal rate of return when shifted |
| 6 | 1 | 6 | CHS | DATE | DATE | Toggle sign of the entry and calculate date difference when shifted |
| 7 | 1 | 7 | 7 | BEG | BEG | Enter digit 7 and select beginning-of-period timing when shifted |
| 8 | 1 | 8 | 8 | END | END | Enter digit 8 and select end-of-period timing when shifted |
| 9 | 1 | 9 | 9 | MEM | MEM | Enter digit 9 and open the memory/register function when shifted |
| 10 | 1 | 10 | ÷ | x² | — | Divide the two top stack values |
| 11 | 2 | 1 | yˣ | xʸ | — | Raise the stack base to the entered exponent |
| 12 | 2 | 2 | 1/x | eˣ | — | Replace X with its reciprocal |
| 13 | 2 | 3 | %T | LN | — | Calculate X as a percentage of the accumulated total |
| 14 | 2 | 4 | Δ% | FRAC | — | Calculate percentage change between the two top values |
| 15 | 2 | 5 | % | INT | — | Calculate the percentage of the Y register |
| 16 | 2 | 6 | EEX | ΔDYS | — | Enter an exponent and calculate date difference when shifted |
| 17 | 2 | 7 | 4 | D.MY | — | Enter digit 4 and use day-month-year date format when shifted |
| 18 | 2 | 8 | 5 | M.DY | — | Enter digit 5 and use month-day-year date format when shifted |
| 19 | 2 | 9 | 6 | x̄w | — | Enter digit 6 and calculate weighted mean when shifted |
| 20 | 2 | 10 | × | x² | — | Multiply the two top stack values |
| 21 | 3 | 1 | R/S | PSE | — | Start/stop program execution or pause the visible operation |
| 22 | 3 | 2 | SST | BST | — | Advance one program step or move backward when shifted |
| 23 | 3 | 3 | R↓ | GTO | — | Rotate the RPN stack down or jump to a program line when shifted |
| 24 | 3 | 4 | x↔y | x↔y | — | Exchange the X and Y stack registers |
| 25 | 3 | 5 | CLX | x=0 | — | Clear the X register or test X for zero when shifted |
| 26 | 3 | 6 | ENTER | = | — | Lift the RPN stack and commit the current entry; span row 3 and row 4 |
| 27 | 3 | 7 | 1 | x,r | — | Enter digit 1 or convert rectangular/polar coordinates when shifted |
| 28 | 3 | 8 | 2 | r,n | — | Enter digit 2 or calculate rate/period conversion when shifted |
| 29 | 3 | 9 | 3 | n,i | — | Enter digit 3 or solve the corresponding TVM register when shifted |
| 30 | 3 | 10 | − | — | — | Subtract the two top stack values |
| 31 | 4 | 1 | ON | OFF | — | Turn the calculator display on or off |
| 32 | 4 | 2 | f | — | — | Arm the orange shifted-function layer |
| 33 | 4 | 3 | g | — | — | Arm the blue shifted-function layer |
| 34 | 4 | 4 | STO | ( | — | Store X in the selected register or open a grouped expression |
| 35 | 4 | 5 | RCL | ) | — | Recall the selected register or close a grouped expression |
| 36 | 4 | 6 | ENTER (continuação) | = | — | Visual continuation of the spanning ENTER control; no second action |
| 37 | 4 | 7 | 0 | ∫ | — | Enter digit 0 or integrate when shifted |
| 38 | 4 | 8 | . | s | — | Enter decimal point or calculate standard deviation when shifted |
| 39 | 4 | 9 | Σ+ | Σ− | — | Add a data pair to statistics or remove it when shifted |
| 40 | 4 | 10 | + | LST x | — | Add the two top stack values or recall the last X value when shifted |

The visual gate must assert all 40 row/column slots, the spanning ENTER
geometry, the three legend-color placements, and a real click-driven action
for every physical control. It must also prove that the ten complex financial
operations are reachable through the same rendered interface.

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
