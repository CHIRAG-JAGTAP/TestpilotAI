# b01_arithmetic
* Category: arithmetic / branching   * Complexity: low   * Split: development
* Dependencies: none (stdlib only)   * Existing tests: none
Expected behaviour: `clamp` bounds a value (ValueError if low > high); `sign` returns -1/0/1;
`safe_divide` raises ZeroDivisionError for b == 0; `grade` maps 0-100 to A/B/C/F and rejects
out-of-range scores; `is_even` tests parity; `Counter.add` accumulates non-negative amounts.
