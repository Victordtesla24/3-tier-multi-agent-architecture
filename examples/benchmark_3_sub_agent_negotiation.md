# Benchmark 3: Autonomous Interface Negotiation

**Description:**
This benchmark tests the parallel execution capabilities of L2 Sub-Agents and their ability to align on a shared, undocumented interface contract without breaking the L1 single source of truth.

**Input Data:**
<input_data>
Build a distributed microservice system in Go.
Requirement 1: Create an `AuthService` that generates JWT tokens.
Requirement 2: Create a `PaymentService` that verifies those exact JWT tokens before processing a transaction.
Constraint: Do not use any external auth libraries (e.g., jwt-go). Implement the token signing and verification logic purely using the standard crypto libs.
</input_data>

**Expected Execution Output Elements:**
- **Exact-Match Requirement**: The L1 Orchestrator must spawn two distinct L2 Sub-Agents (one for Auth, one for Payment).
- **Interface Alignment**: The agents must establish a shared secret algorithm (e.g., HMAC-SHA256) and token payload schema. Both the `AuthService` generator and `PaymentService` verifier code must mathematically match this emergent schema.
- **Single Source of Truth**: The shared signing logic/keys must be consolidated into a single internal package (e.g., `pkg/crypto/jwt.go`) by the L1 agent dynamically, rather than duplicated in both services.

**Benefits Showcased:**
Demonstrates the architecture's capacity for parallel decomposition, cross-agent component synchronization, and strict DRY (Don't Repeat Yourself) code generation.
