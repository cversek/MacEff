# Java Testing (with Android)

**Version**: 1.0
**Tier**: LANG
**Category**: Java
**Status**: ACTIVE
**Updated**: 2026-10-31
**Parent**: base/development/testing.md

---

## Policy Statement

How the base testing policy is carried out in Java and on Android. The base policy's discipline (a few strategic tests per feature, a red proof before trusting a green one, targeted runs during work and the full suite before a PR) applies unchanged.

## CEP Navigation Guide

**1 Where Tests Live**
- Local JVM test or device test: which, and why?

**2 Framework and Dependencies**
- Which test framework, and what must be on the test classpath?

**3 Doubles**
- Fakes, mocks or Robolectric: which first?

**4 Known Failures**
- How do I keep a failing test without deleting or weakening it?

**5 Running**
- What command runs the tests, and what runs in CI?

=== CEP_NAV_BOUNDARY ===

## 1 Where Tests Live

Local JVM tests in `src/test` by default; `src/androidTest` only for what needs a device or the real framework (sensors, rendering, USB) ([what to test](https://developer.android.com/training/testing/fundamentals/what-to-test)). A class that can't be tested locally is a signal to move its logic out of the framework (coding standards 1.1), not to reach for a device test. Cover the edges: zero, the boundaries of every fixed-width field, malformed input.

## 2 Framework and Dependencies

JUnit 4 (`testImplementation 'junit:junit:4.13.2'`), which the Android documentation covers ([local tests](https://developer.android.com/training/testing/local-tests)); JUnit 5 needs a third-party plugin and is a project decision.

Android framework classes on the local test classpath are stubs. Do not set `unitTests.returnDefaultValues = true`, which "can let failing tests pass" ([local tests](https://developer.android.com/training/testing/local-tests)). Where a test needs a real implementation of a library that Android also ships (`org.json` is the common case), add that library as a `testImplementation` dependency, and confirm the test fails without it so the stub isn't silently in use.

## 3 Doubles

Fakes before mocks; avoid spies ([test doubles](https://developer.android.com/training/testing/fundamentals/test-doubles)). Robolectric is the last resort for a unit test: prefer removing the framework dependency ([Robolectric](https://developer.android.com/training/testing/local-tests/robolectric)).

## 4 Known Failures

A test for behavior that is known to be wrong stays in the suite, marked `@Ignore("known failure (#N): what is wrong")`, so the report counts it as skipped ([@Ignore](https://junit.org/junit4/javadoc/latest/org/junit/Ignore.html)). Its assertion states the correct behavior. It is never deleted, commented out or weakened. A test that cannot be written yet because the code isn't reachable is named in the test class's comment with its issue.

## 5 Running

`./gradlew testDebugUnitTest` locally; in CI on a Linux runner with the project's pinned JDK, keeping the test reports as an artifact. `./gradlew lint` runs in the same CI job (coding standards 6.2).
