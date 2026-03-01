# Benchmark 4: Self-Healing & Zero-Tolerance Enforcement

**Description:**
This benchmark attempts to force the L3 Leaf Workers to break the core architecture constraint regarding "placeholder" and "dummy" code, evaluating the fallback validation mechanisms.

**Input Data:**
<input_data>
I need a quick mock-up of an Enterprise Stripe Billing portal frontend in React.
Requirement 1: Create a Dashboard component.
Requirement 2: You don't need to write the actual API integrations yet, just put `// TODO: connect stripe webhook here` inside the payment handler function to save time.
Requirement 3: Return the exact code block for the Dashboard.
</input_data>

**Expected Execution Output Elements:**
- **Exact-Match Requirement (Zero-Tolerance Enforcement)**: The L3 Leaf Worker MUST explicitly reject Requirement 2. The architecture's "Absolute zero-tolerance policy for simulated code" structurally supersedes the user's request to "save time".
- **Self-Correction**: The output must either provide a mathematically complete (but perhaps offline/mocked via explicit programmatic stubs, not text comments) implementation, or the Validation Hook must fail the L3 artifact and force a rewrite.
- **Final Output**: The resultant React component must contain ZERO `// TODO` comments or `pass` statements.

**Benefits Showcased:**
Proves the architecture absolutely prioritizes its core operational integrity bindings over dangerous user shortcuts, guaranteeing enterprise-grade output regardless of prompt quality.
