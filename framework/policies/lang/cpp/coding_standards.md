# C++ Coding Standards (with JNI and the Android NDK)

**Version**: 1.0
**Tier**: LANG
**Category**: C++
**Status**: ACTIVE
**Updated**: 2026-10-31
**Parent**: base/development/coding_standards.md

---

## Policy Statement

C++-specific standards for code written within MacEff framework projects, with a section on JNI and the Android NDK. They layer on the base coding standards; where the two differ, the base policy wins and this one is amended. The C++ Core Guidelines ([isocpp](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines)) are the reference; this policy names the rules an agent most needs and adds what the guidelines don't cover.

## Scope

Any C++ source an agent writes or edits, including native code loaded through JNI. The Java side of a JNI boundary belongs to the Java policy. Vendored third-party code is read and patched minimally, not restyled.

## CEP Navigation Guide

**1 Resources and Ownership**
- Who owns this object, and what releases it?

**2 Types, Conversions and Units**
- When is a narrowing conversion allowed?
- How do units and clocks show up in types?

**3 Errors**
- How does a failure leave a function, and how does it cross into Java?
- Why error codes rather than exceptions in code loaded through JNI?

**4 Clocks and Time**
- Which clock does a timestamp come from, and may two timestamps be compared?

**5 JNI and the NDK**
- How thin is the JNI layer, and where does testable logic live?
- What must I do about references, exceptions and threads at the boundary?

**6 Tests**
- How is native logic tested without a device, and how is a known failure marked?

**7 Build, Warnings and Sanitizers**
- Which checks run on native builds?

**8 Anti-Patterns**

**9 Amendment**

=== CEP_NAV_BOUNDARY ===

## 1 Resources and Ownership

### 1.1 Every resource has an owning handle

Memory, files, locks and JNI global references are held by RAII objects, never by hand-paired acquire and release (Core Guidelines [R.1](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rr-raii), E.6). No bare `new` or `delete`: `std::make_unique`, containers or scoped objects ([R.11](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rr-newdelete)). Locks only through `std::lock_guard` or `std::scoped_lock` ([CP.20](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rconc-raii)).

### 1.2 Ownership is in the type

`std::unique_ptr` (preferred) or `std::shared_ptr` owns; a raw `T*` or `T&` never does ([R.20](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rr-owner), I.11). A function that only uses an object takes `T*` or `T&`, not a smart pointer ([F.7](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rf-smart)). Rule of zero; if any of copy, move or destructor is defined or deleted, all are ([C.20, C.21](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rc-zero)).

## 2 Types, Conversions and Units

### 2.1 Initialize everything; brace-initialize

Every object is initialized, with `{}` where possible so a narrowing initialization is a compile error ([ES.20, ES.23](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Res-always)). `const` by default ([Con.1](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Rconst-immutable)).

### 2.2 No silent narrowing

A lossy conversion (64-bit nanoseconds to 32 bits, `double` to `float`, a length into a byte) is an explicit, named, range-checked conversion ([ES.46](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Res-narrowing)), and a boundary test feeds the first value that doesn't fit.

### 2.3 Units and clocks live in the type

Durations are `std::chrono` types, not bare integers; interfaces are strongly typed ([I.4, P.1](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Ri-typed)). Section 4 applies this to clocks.

## 3 Errors

### 3.1 Error codes in code loaded through JNI; nothing crosses an entry point

Code that runs inside an Android app through JNI reports failure with error codes or result types, not exceptions, as Android's JNI guidance advises: "C++ exceptions, generally discouraged on Android, must not be thrown across the JNI transition boundary from C++ code to managed code" ([JNI tips](https://developer.android.com/training/articles/perf-jni)). ndk-build disables them by default; CMake enables them ([C++ library support](https://developer.android.com/ndk/guides/cpp-support)). Error codes are used systematically ([E.25, E.27](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#Re-no-throw-codes)); RAII still releases resources on every path. Elsewhere the Core Guidelines' preference for exceptions applies (E.2, E.14). Third-party code that throws is wrapped so no exception reaches a JNI entry point: each entry point catches and converts.

## 4 Clocks and Time

### 4.1 Each clock gets its own timestamp type

Every timestamp that crosses a function or module boundary has a type per clock (for example distinct boot-clock and monotonic-clock time points, or `std::chrono::time_point` over a custom clock), so two clocks cannot be subtracted or compared by accident. Conversion between clocks happens in one named function, from a measured offset.

**The clocks:** `CLOCK_MONOTONIC` "does not count time that the system is suspended"; `CLOCK_BOOTTIME` is the same "except that it also includes any time that the system is suspended" ([clock_gettime(2)](https://man7.org/linux/man-pages/man2/clock_gettime.2.html)). Android sensor event timestamps are on the `elapsedRealtimeNanos()` base, the boot clock ([SensorEvent](https://developer.android.com/reference/android/hardware/SensorEvent), [ASensorEvent](https://developer.android.com/ndk/reference/struct/a-sensor-event)). Other sources (camera frames, for one) may use a different base and are checked, not assumed.

**Why it binds:** observed, a head tracker's state was stamped with sensor times on the boot clock while the caller requested a pose at a `CLOCK_MONOTONIC` time. The difference, all suspend time since boot, became a prediction step of about 2.5 s backwards: the pose was right at rest and wrong in proportion to head speed. With typed clocks the call would not have compiled.

### 4.2 A test simulates the offset

Code that combines times from more than one source has a unit test that feeds the sources with a simulated suspend offset between them and asserts the result stays within its bound.

## 5 JNI and the NDK

### 5.1 The JNI layer is thin

JNI entry points convert arguments, call plain C++ and convert results; logic lives in plain C++ that has no `jni.h` include and is tested on the host. The plain C++ builds as a host target with no `jni.h` on its include path, so a JNI include in it fails the host build instead of waiting for review. Keep calls across the boundary few and small ([JNI tips](https://developer.android.com/training/articles/perf-jni)).

### 5.2 References, exceptions and threads

From [JNI tips](https://developer.android.com/training/articles/perf-jni):
- Local references die when the native method returns; delete them inside loops (only 16 are guaranteed). A cached `jclass` is promoted with `NewGlobalRef`; `jmethodID` and `jfieldID` are cached as they are. References are compared with `IsSameObject`, never `==`.
- After any `Call*Method`, check for a pending exception and return or clear it before the next JNI call.
- A `JNIEnv` is never shared between threads. Cache the `JavaVM`; a native thread calls `AttachCurrentThread` before any JNI call and `DetachCurrentThread` before it exits.

### 5.3 CheckJNI in debug

Debug and test builds run with CheckJNI on (a debuggable app, or `adb shell setprop debug.checkjni 1`).

## 6 Tests

Plain C++ logic is tested with GoogleTest on the host; device runs are for code that needs the Android runtime. `EXPECT_*` by default, `ASSERT_*` only when the rest of the test cannot proceed ([primer](https://google.github.io/googletest/primer.html)). A known failure is a `DISABLED_` test naming its issue; `GTEST_SKIP()` is for runtime preconditions such as missing hardware ([advanced](https://google.github.io/googletest/advanced.html)). An assertion is never weakened to make a test pass. (No official Android page covers host testing of NDK app code; this is the policy's choice.)

## 7 Build, Warnings and Sanitizers

- Native test builds use HWASan on arm64 where the device supports it (Android 14 or later); plain ASan is unsupported for new work ([HWASan](https://developer.android.com/ndk/guides/hwasan), [ASan](https://developer.android.com/ndk/guides/asan)).
- `-Wall -Wextra` on the project's own sources, with `-Werror` in CI; vendored sources are exempt and listed. (A convention, not an NDK mandate.) The build pins `ndkVersion`, so a toolchain update that adds a warning fails on purpose, in its own change.

## 8 Anti-Patterns

- **Timestamps from two clocks subtracted** (4.1).
- **A cast as a range check** (2.2).
- **Logic in the JNI function** (5.1).
- **Ignoring a pending Java exception after a call** (5.2).
- **A disabled test with no issue named, or a weakened assertion** (6).

## 9 Amendment

Amend this policy when a rule here is shown wrong by a measured failure, stating the failure generically in the rule's section.
