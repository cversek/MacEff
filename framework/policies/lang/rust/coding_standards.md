# Rust Coding Standards

**Version**: 1.0
**Tier**: LANG
**Category**: Rust
**Status**: ACTIVE
**Updated**: 2026-09-20
**Parent**: base/development/coding_standards.md

---

## Policy Statement

Rust-specific standards for code written within MacEff framework projects, with
the base policy's Error Visibility Stance as the parent: a failure is surfaced
where it happens, typed so the caller can act on it, and never converted into a
plausible value. This policy exists to be **pre-registered**: it is written before
the code it will judge, so that review measures work against a standard that was
agreed in advance rather than against a reviewer's taste on the day.

Every criterion below carries a **Recognised in review by** clause — the observable
a reviewer looks for. A criterion that cannot be recognised in a diff is a wish,
not a standard, and does not belong here.

## Scope

All Rust code in MacEff framework projects: services, CLIs, libraries and their
tests. Sections 6 and 7 bind *additionally* wherever code touches money, keys, or an
external chain; the parent domain policy (where a deployment has one) names which
crates those are.

---

## CEP Navigation Guide

**0 Errors**
- What does the Error Visibility Stance look like in Rust?
- When is a typed error required and when is an opaque one acceptable?
- Where may `unwrap`, `expect` and `panic!` appear, and where never?
- How is an invariant asserted without a panic on the hot path?

**1 Ownership, Borrowing and API Shape**
- What does idiomatic ownership look like at a function boundary?
- When is `clone` a smell and when is it correct?
- What must a public type promise about `Send`/`Sync`?
- How are units and identifiers kept from being confused (newtypes)?

**2 `unsafe`**
- When is `unsafe` permitted at all?
- What must accompany every `unsafe` block?
- Who reviews it?

**3 Async and Concurrency**
- What may never happen inside an async task?
- How is cancellation handled?
- What does a bounded system look like (channels, timeouts, backpressure)?
- Which runtime, and how many?

**4 Dependencies and Supply Chain**
- What gates a new dependency?
- What must be committed, and what must CI run?
- How are features minimised?
- What does "audited" mean here?

**5 Lints, Formatting and Toolchain**
- What is the clippy baseline and how is a lint waived?
- How is the toolchain pinned?
- What does CI enforce?

**6 Tests, and TDD Where It Is Mandatory**
- Where is TDD mandatory and how is it evidenced?
- What is the minimum test shape for a feature?
- When are property tests required?
- How is a test proven to bite (mutation check)?

**7 Secrets, Logging and Observability**
- How is a secret typed so it cannot leak by accident?
- What may a log line carry, and what never?
- What does structured observability look like?

**8 Anti-Patterns**
- The list, each with the observable that gives it away.

**9 Amendment**
- How is this standard changed, and by whom?

---

## 0 Errors

### 0.1 Typed errors at every boundary the caller can act on

Library and service code returns `Result<T, E>` where `E` is an enum the caller can
match on (`thiserror` is the conventional derive). An opaque error (`anyhow::Error`,
`Box<dyn Error>`) is acceptable **only at the binary's outermost edge**, where the
only remaining action is to report and exit. Converting a typed error into an opaque
one below that edge destroys the information the parent policy exists to preserve.

**Recognised in review by**: a `pub fn` in a library crate returning `anyhow::Result`
or `Box<dyn Error>`; a `?` that crosses a module boundary without a `From` impl or
`.map_err` naming the new variant; an error enum with a catch-all `Other(String)`
variant carrying information a caller would need to branch on.

### 0.2 No panics on the hot path

`unwrap()`, `expect()`, indexing with `[]` on caller-supplied data, integer
arithmetic that can overflow, and `panic!` are **forbidden in request-handling,
scheduling, signing and submission paths**. They are acceptable in: tests; `build.rs`;
`main` before the runtime starts; and on an invariant that is *proved* in a comment
immediately above (a value the type system guarantees but cannot express).

**Recognised in review by**: `unwrap`/`expect`/`[i]` in a non-test module without a
`// INVARIANT:` comment on the preceding line; `#![deny(clippy::unwrap_used,
clippy::expect_used, clippy::indexing_slicing, clippy::arithmetic_side_effects)]`
absent from a crate this policy names as hot-path.

### 0.3 A failure is reported where it is known, once

Errors are logged (structured, §7) at the point where the context to explain them
exists — usually where they are handled, not where they are created — and are not
logged again at every frame they pass through. A swallowed error (`let _ = fallible();`,
`.ok()` discarding a `Result` that carried information, `if let Ok(x) = ...` with no
`else`) is the Rust spelling of the parent policy's silent `pass`.

**Recognised in review by**: `let _ =` on a `Result`; `.ok()` on a `Result` whose
error is not provably uninteresting (comment required); `if let Ok` without an
`else` arm that reports; the same error string appearing in two `tracing::error!`
calls up one call chain.

### 0.4 Invariants are types, then debug assertions, then comments

Prefer making the illegal state unrepresentable (an enum, a newtype with a validated
constructor). Where that is impossible, `debug_assert!` documents the invariant in
tests and costs nothing in release. A comment is the last resort and must say *why*
the invariant holds.

**Recognised in review by**: a `bool` parameter selecting behaviour where an enum
would name it; a `String` carrying something with a grammar (an address, an id); a
function that validates its input and then accepts the same input elsewhere unvalidated.

---

## 1 Ownership, Borrowing and API Shape

### 1.1 Borrow at the boundary, own where you store

Functions take `&str`, `&[T]`, `impl AsRef<Path>` when they only read; they take
ownership (`String`, `Vec<T>`) when they store. Returning borrowed data from a
function that computed it is a lifetime puzzle for every caller; return owned data
unless the borrow is the whole point (a view into a buffer).

**Recognised in review by**: `fn f(s: String)` that only reads `s`; `fn f(s: &String)`
or `&Vec<T>` (should be `&str`, `&[T]`); a `.clone()` inside a loop on a value the
loop only reads.

### 1.2 `clone` is a decision, not a fix

A `clone()` added to satisfy the borrow checker is a smell; the shape of the
ownership is wrong. A `clone()` of an `Arc`, a small `Copy`-like value, or data that
genuinely has two owners is correct and needs no comment.

**Recognised in review by**: `clone()` on a large owned value where a borrow would
compile with a small restructuring; `Rc`/`Arc<Mutex<_>>` wrapping a value that has one
owner.

### 1.3 Newtypes for anything with a unit or an identity

Quantities (an amount in the smallest unit, a block number, a duration in ms) and
identifiers (a token id, a pool address, a strategy id) are **newtypes**, not bare
integers or strings. Arithmetic between different units does not compile.
Display and parse are implemented on the newtype so formatting lives in one place.

**Recognised in review by**: two `u64` parameters in a signature where swapping them
would compile; a `u128` "amount" added to a `u64` "block"; `String` where a
`FromStr` newtype exists.

### 1.4 Public types state their thread-safety

A `pub` type that is meant to cross tasks is `Send + Sync` and a test asserts it
(`fn assert_send<T: Send>() {}`). Interior mutability is `Mutex`/`RwLock` from the
runtime's crate in async code, never `RefCell` across an `.await`.

**Recognised in review by**: a `pub struct` held in a shared handle with no
`Send`/`Sync` assertion in its tests; `std::sync::Mutex` held across an `.await`.

### 1.5 `#[must_use]` on results that are easy to drop

Builders, guards and any function whose return value carries the whole effect are
`#[must_use]`.

**Recognised in review by**: a builder or a `Result`-returning fn whose value is
discarded in a call site; the lint `clippy::must_use_candidate` firing on a `pub fn`.

---

## 2 `unsafe`

### 2.1 Forbidden by default

Every crate carries `#![forbid(unsafe_code)]` unless it is one of the crates a
project's domain policy explicitly names as needing it (FFI, a proven hot loop).
`forbid`, not `deny`: it cannot be overridden by an inner `allow`.

### 2.2 Every block carries its proof and its reviewer

An `unsafe` block is preceded by a `// SAFETY:` comment stating the invariant the
compiler cannot check and why it holds here. The pull request that introduces it
names a **second reviewer** in its body, and that reviewer's approval is on the PR
before merge. A soundness argument that fits in a comment is the only kind allowed;
one that needs a paper does not belong in this codebase.

**Recognised in review by**: `#![forbid(unsafe_code)]` missing from a crate root;
`unsafe` without a `// SAFETY:` line immediately above; an `unsafe` PR with one
approval.

---

## 3 Async and Concurrency

### 3.1 Never block the runtime

No synchronous I/O, no `std::thread::sleep`, no CPU-bound loop longer than a
scheduler tick inside an async task. Blocking work goes through `spawn_blocking` or
a dedicated thread with a channel.

**Recognised in review by**: `std::fs`, `std::net`, `std::thread::sleep`, or a
`while` over a large collection inside an `async fn`; `block_on` anywhere but `main`
and tests.

### 3.2 Cancellation is a normal exit

Every `select!` arm, timeout and task handle is written knowing the future may be
dropped at any `.await`. State that must not be left half-written is guarded by a
drop guard or committed in one step. A task that must run to completion is
`spawn`ed and its `JoinHandle` is awaited or explicitly detached with a comment.

**Recognised in review by**: a multi-step write (two `await`s between which the state
is inconsistent) with no guard; a `JoinHandle` dropped without a comment; `select!`
over a future that is not cancel-safe (documented as such by its crate).

### 3.3 Everything is bounded

Channels have a capacity; every external call has a timeout; every retry has a
ceiling and a jittered backoff; every queue has a policy for what happens when it is
full (drop-newest, drop-oldest, or apply backpressure — chosen, and stated).

**Recognised in review by**: `unbounded_channel`; a network call without
`tokio::time::timeout` or an equivalent client-level deadline; a retry loop with no
`max_attempts`; `Vec` growth from an external stream with no cap.

### 3.4 One runtime

A binary owns one runtime, created in `main` (or by `#[tokio::main]`), and passes
handles down. Libraries never create runtimes and never depend on a specific
runtime's globals beyond the one the project has chosen.

**Recognised in review by**: `Runtime::new()` or `#[tokio::main]` outside `main`;
`block_on` in a library.

---

## 4 Dependencies and Supply Chain

### 4.1 A new dependency is a reviewed decision

Adding a crate is justified in the PR: what it does that the standard library or an
existing dependency does not, its maintenance signal (last release, open soundness
issues), its transitive weight (`cargo tree -e features`), and its licence. A
dependency that pulls a second async runtime, a second TLS stack or a second
serialisation framework is refused unless the PR argues for it.

**Recognised in review by**: a `Cargo.toml` diff adding a crate with no paragraph in
the PR body; `cargo tree -d` showing a duplicated major version after the change.

### 4.2 Lockfile committed; `--locked` in CI

`Cargo.lock` is committed for binaries and services. CI builds and tests with
`--locked` so a drifted lockfile fails the build rather than silently resolving to
something newer.

### 4.3 Minimal features

Dependencies are declared with `default-features = false` and the features actually
used listed, unless the defaults are demonstrably all needed (state it in a comment
on the line).

**Recognised in review by**: a heavy crate (`tokio`, `reqwest`, `sqlx`, `alloy`) with
default features and no comment.

### 4.4 Audited means the tools ran, on this lockfile, in CI

- `cargo audit` (RustSec advisories) — fails CI on any unreviewed advisory.
- `cargo deny check` with a committed `deny.toml` — licences allowed by list, banned
  crates, duplicate-version policy, sources restricted to crates.io (or a named
  mirror). Git dependencies are refused by default; an exception is pinned to a
  `rev` and justified.
- A CycloneDX SBOM (`cargo cyclonedx` or the project's SBOM tool) regenerated on
  every release and stored where the deployment keeps SBOMs.

**Recognised in review by**: a `Cargo.lock` change without the audit/deny jobs in the
CI run; a `git = "..."` dependency without `rev`; an advisory waived in `deny.toml`
without a comment naming the reviewer and the reason.

### 4.5 MSRV declared

`rust-version` is set in `Cargo.toml` and CI tests on it as well as on stable.

---

## 5 Lints, Formatting and Toolchain

### 5.1 Baseline

Every crate root:

```rust
#![forbid(unsafe_code)]                    // §2; removed only by a named exception
#![deny(warnings)]                         // in CI via RUSTFLAGS, not in source (see 5.3)
#![warn(clippy::pedantic, clippy::nursery)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::indexing_slicing,
        clippy::arithmetic_side_effects, clippy::panic, clippy::todo,
        clippy::unimplemented, clippy::dbg_macro, clippy::print_stdout,
        clippy::print_stderr)]              // the last two: use tracing (§7)
#![warn(missing_docs, rust_2018_idioms, unreachable_pub)]
```

`pedantic` and `nursery` are *warnings*; individual lints from them are promoted to
`deny` as the project learns which ones bite. A test module may `#[allow]` the
`unwrap_used`/`expect_used` family at module scope — tests are the one place a
panic is the right failure.

### 5.2 A waiver names its reason

Every `#[allow(clippy::...)]` outside a test module has a `// reason:` comment on the
same or preceding line, or uses the `reason = "..."` attribute argument. A waiver
without a reason is removed by the next reviewer.

**Recognised in review by**: `#[allow(` with no reason; a crate-wide `allow` of a
lint this section denies.

### 5.3 Toolchain pinned, formatting mechanical

`rust-toolchain.toml` pins the channel (stable, with a version) and components
(`clippy`, `rustfmt`). `cargo fmt --check` and `cargo clippy --all-targets
--all-features -- -D warnings` run in CI; formatting is never discussed in review
because it cannot differ.

**Recognised in review by**: a review comment about formatting (the tooling is
broken, fix that instead); `rust-toolchain.toml` absent or unpinned.

---

## 6 Tests, and TDD Where It Is Mandatory

### 6.1 TDD is mandatory for chain-touching and money-touching code

For every crate the domain policy names (signing, submission, calldata construction,
accounting), the failing test is **committed before** the code that passes it, in
its own commit, so a reviewer can see red precede green in the history. A PR that
adds such code with tests only in the final commit is returned.

**Recognised in review by**: `git log --reverse` on the PR showing the test file's
first commit after the implementation's; a test that passes on the parent commit
(it tests nothing new).

### 6.2 Minimum shape per feature

Four to six focused tests: the happy path, each error variant the feature can
return, the boundary (empty, max, zero), and the concurrency or cancellation case
where the feature is async. One test per assertion class, named for the behaviour
(`refuses_a_transfer_to_an_unlisted_recipient`), not the function.

### 6.3 Property tests where the input space is a grammar

Encoders, decoders, parsers, arithmetic on quantities, and anything with a
round-trip (`encode(decode(x)) == x`) carry a `proptest` (or equivalent) with a
shrinking strategy. A hand-picked example is not a test of a grammar.

**Recognised in review by**: a `FromStr`/`Display` pair, an ABI encoder, or a
unit-conversion with only example-based tests.

### 6.4 Every new test is shown to bite

Before a PR is opened, the author plants the defect the test guards against (or
reverts the fix) and records that the test failed, then restores. The PR body states
this in one line. A green test that has never been red is a comment.

**Recognised in review by**: the PR body lacking the red/green line for new tests; a
test whose assertion cannot fail (`assert!(true)`, asserting on the fixture's own
input).

### 6.5 Tests are hermetic

No network, no clock, no filesystem outside `tempdir`, no environment except what
the test sets. Time is injected (a `Clock` trait or a frozen instant); the chain is a
fake or a fork behind the project's port trait. A test that needs the real network
is an integration test behind a feature flag and is not run by default.

**Recognised in review by**: `SystemTime::now()`, `Instant::now()` or `env::var` in a
unit test; a test that fails when run offline.

---

## 7 Secrets, Logging and Observability

### 7.1 A secret is a type

Key material, tokens and credentials are held in a wrapper that: does not implement
`Debug`/`Display` (or implements them as `[REDACTED]`), zeroises on drop
(`zeroize`), and exposes bytes only through an explicit accessor whose call sites are
countable. `secrecy::SecretString`/`SecretVec` or an in-project equivalent.

**Recognised in review by**: `String`/`Vec<u8>` fields named `key`, `secret`,
`token`, `mnemonic`; `#[derive(Debug)]` on a struct containing one; a secret
passed as a `&str` parameter.

### 7.2 Logs carry structure, never secrets, never raw payloads

`tracing` with typed fields (`tracing::info!(pool = %pool_id, weight, "voted")`), not
formatted strings. Never logged: key material, full calldata of a signed
transaction, a raw RPC response body, a mnemonic, an auth header. Addresses and
ids are fine — they are public — but the policy of the deployment decides which
*private* identifiers (wallet addresses under management) are redacted in logs
that leave the host.

**Recognised in review by**: `println!`/`eprintln!` in non-test code;
`format!("{:?}", tx)` on a signed transaction; a `tracing` span field carrying a
type from §7.1.

### 7.3 Every stage has a timer

Latency-sensitive paths record a duration per stage as a structured field or a
metric, from the first byte read to the last byte confirmed. "It felt fast" is not
an observation.

**Recognised in review by**: a pipeline of `await`s with no `Instant` per stage and
no histogram; a PR claiming a latency without a number in the test output.

---

## 8 Anti-Patterns

| Anti-pattern | Observable that gives it away |
|---|---|
| Stringly-typed identifiers and amounts | two `String`/`u64` parameters swappable without a compile error |
| Error laundering | `.map_err(\|_\| MyError::Other)` discarding the cause; `anyhow` below the binary edge |
| Silent discard | `let _ = fallible()`; `.ok()` without a comment |
| Panic as control flow | `unwrap` on `parse()` of external input; `[i]` on a caller's slice |
| Blocking the runtime | `std::fs`/`std::thread::sleep` in an `async fn` |
| Unbounded anything | `unbounded_channel`; retry without a ceiling; a call without a timeout |
| Feature bloat | heavy crates with default features and no comment |
| Waiver without reason | `#[allow(clippy::…)]` bare |
| Green-only tests | a test whose first commit follows the implementation; no red/green line in the PR |
| Secret in a `String` | `Debug` derived on a struct with a `key` field |
| Formatting in review | a human comment about whitespace |
| Clock in a test | `Instant::now()` in `#[test]` |

---

## 9 Amendment

This standard is amended by pull request, never by an inline `allow` that spreads.
An amendment arises when observed practice is better than the rule — the PR states
the observation (the code that prompted it, the review that noticed), changes the
criterion and its *Recognised in review by* clause together, and appends a Revision
History entry. **The amendment PR is reviewed by someone other than the author of
the code that prompted it.** A criterion that is waived three times without an
amendment is a criterion nobody believes; either amend it or enforce it.

---

**Review procedure**: findings cite a section here by number and quote the observable;
amendments change the criterion and its *Recognised in review by* clause together and are
reviewed by someone other than the author of the code that prompted them (§9). A
deployment that pre-registers this standard before its first Rust code records the
engineers' written reviews below.

## Revision History

- **1.0 — 2026-09-20** — Initial standard. Written for a deployment that pre-registered
  it before its first Rust code, and proposed to the framework as the first `lang/rust`
  policy, the way `lang/python` models a language standard.

## Wiki-Links

[[coding_standards]] [[verification]] [[silent_failure]] [[opsec]]
