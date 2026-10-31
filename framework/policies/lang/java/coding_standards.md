# Java Coding Standards (with Android)

**Version**: 1.0
**Tier**: LANG
**Category**: Java
**Status**: ACTIVE
**Updated**: 2026-10-31
**Parent**: base/development/coding_standards.md

---

## Policy Statement

Java-specific standards for code written within MacEff framework projects, with an Android section. They layer on the base coding standards, which state the discipline; this policy says how it is expressed in Java and on Android. Where the two differ, the base policy wins and this one is amended. Testing specifics are in `testing_java.md`.

## Scope

Any Java source an agent writes or edits: libraries, services and Android apps. Kotlin is out of scope; most current Android guidance is written for Kotlin, and the rules here translate it (executors or a `HandlerThread` for coroutines, a listener interface for flows, constructor injection for a DI framework). The Java side of a JNI boundary is covered here; the native side belongs to the C++ policy.

## CEP Navigation Guide

**1 Structure: Logic Outside the Framework**
- Where does logic go in an Android app so it can be tested without a device?
- What may a class that builds bytes, parses messages or decides routing import?

**2 Threads and Blocking**
- What may wait on the main thread?
- Whose job is it to move blocking work off the main thread?

**3 Data Formats and Boundaries**
- How do I keep a binary layout the same across every code base that reads it?
- What do I check before putting a value into a fixed-width field?

**4 Clocks and Time**
- Which clock does each timestamp come from, and which may be compared?

**5 Errors and Exceptions**
- What do I do with an exception I catch?

**6 Toolchain and Build**
- Which JDK does the build use, and how is that made certain?
- Which static checks run, and where?

**7 Style**
- Which style guide applies, and which of its rules matter most for an agent's edits?

**8 Anti-Patterns**

**9 Amendment**

=== CEP_NAV_BOUNDARY ===

## 1 Structure: Logic Outside the Framework

### 1.1 Activities, Fragments and Services are thin

Protocol handling, parsing, packet building and decisions live in plain classes; the Activity, Service or thread wires them to the framework and does the I/O. "It's a common mistake to write all your code in an Activity" ([architecture guide](https://developer.android.com/topic/architecture)).

**Why it binds:** logic inside an Activity can only be tested on a device. Observed: the layout of several binary packets lived in Activity methods, and its first unit test came only after it was moved into a plain class.

### 1.2 Logic classes take no framework types

A class that decides or computes takes plain values and interfaces through its constructor, not `Context`, `Activity`, `Resources`, `SensorEvent` or a socket ("Don't pass Activity, Context, or Resources as a dependency", [recommendations](https://developer.android.com/topic/architecture/recommendations)). The caller unpacks the framework object. Such a class has no `android.*` import, which is checkable.

## 2 Threads and Blocking

### 2.1 Nothing waits on the main thread

No I/O, long computation, lock contention or synchronous wait for a reply runs on the main thread; each is a listed cause of "Application Not Responding" ([ANR causes](https://developer.android.com/topic/performance/vitals/anr)). A bounded wait is still a wait.

**Why it binds:** observed, a call that waited up to 2 s on the main thread for another thread's reply, made twice per state change, held a sensor listener on the same thread for up to 4 s. The readings were not lost, but arrived in bursts seconds late.

### 2.2 A class that blocks is responsible for its own thread

Each type is main-safe: if it does blocking work, it moves that work off the main thread itself rather than relying on callers ([architecture guide](https://developer.android.com/topic/architecture)). A request that needs a reply takes a callback, or returns a future the caller does not block on from the main thread.

### 2.3 StrictMode in debug builds

Enable `StrictMode` thread and VM policies with `detectAll()` in debug builds ([StrictMode](https://developer.android.com/reference/android/os/StrictMode)). It catches disk and network access on the main thread, not a plain wait, so it does not replace 2.1.

### 2.4 Reply channels carry their request

When replies come back on a queue, each reply names the request it answers. A caller that times out must not leave a reply that the next caller takes as its own.

## 3 Data Formats and Boundaries

### 3.1 One written contract per wire format

A binary or text format read by more than one code base is defined once, as data (codes, field order, types, units, example bytes with decoded values), and each code base tests against that same file. The copies are compared byte for byte by a test.

**Why it binds:** observed, three code bases each carried their own copy of a packet layout; a reader decoded a 24-byte payload as 20 bytes and a stream write landed in the wrong method, and only a shared contract with examples caught both in seconds.

### 3.2 Narrowing into a fixed-width field is checked

Before a value goes into a field narrower than its type (a length into a byte, a counter into a short), the code checks the range and refuses or splits, and a boundary test sends the first value that does not fit. A cast is not a check.

**Why it binds:** observed, a frame length cast to one byte was silently wrong above 255, which would desynchronize every packet after it.

## 4 Clocks and Time

### 4.1 Every timestamp names its clock

A field or variable holding a time says which clock it came from (for example `atElapsedNanos`, or a comment on the field). `SensorEvent.timestamp` is on the `SystemClock.elapsedRealtimeNanos()` base on current devices ([NDK sensor event](https://developer.android.com/ndk/reference/struct/a-sensor-event)); it is compared only with that clock, never with `System.nanoTime()` or `currentTimeMillis()`. Because devices have varied, code that depends on the base measures the offset at startup and logs it rather than assuming it.

### 4.2 Two clocks are never mixed in one computation

A difference or a prediction horizon is computed from two times on the same clock. Times from different clocks are converted through a measured offset, stated where it is applied.

## 5 Errors and Exceptions

### 5.1 A caught exception is handled, or rethrown with context

"It is very rarely correct to do nothing in response to a caught exception" ([Google Java Style 6.2](https://google.github.io/styleguide/javaguide.html)). An empty catch states why in a comment. A thread's top-level handler logs the exception and the state it ends, so a dropped connection is visible as a dropped connection.

## 6 Toolchain and Build

### 6.1 The toolchain is pinned

The build declares its Java toolchain, with `sourceCompatibility` and `targetCompatibility` equal ("always specify the Java toolchain", [JDKs](https://developer.android.com/build/jdks)), and the JDK is one the Android Gradle Plugin version supports (AGP 7.4: JDK 11; AGP 8.x: JDK 17, [AGP 7.4 notes](https://developer.android.com/build/releases/past-releases/agp-7-4-0-release-notes)).

**Why it binds:** observed, a newer JDK on the machine broke the dexer with no code change; the build had picked up whatever `JAVA_HOME` said.

### 6.2 Lint runs in CI

`./gradlew lint` runs in CI with `abortOnError` left on; existing warnings go into a committed baseline, not a disabled check ([lint](https://developer.android.com/studio/write/lint)). Lint does not run as part of a normal build.

### 6.3 Error Prone: optional, strongly encouraged

Error Prone ([errorprone.info](https://errorprone.info)) catches classes of bugs at compile time that lint does not, narrowing conversions among them. Wire it into the Java compile tasks with the `net.ltgt.errorprone` plugin and a pinned version; the plugin has no specific Android support, so the wiring is manual. A project that doesn't adopt it says why.

## 7 Style

Google Java Style ([guide](https://google.github.io/styleguide/javaguide.html)) applies to every new or touched file, whatever the file's older style: an edit brings what it touches up to the standard, rather than matching the code around it. The rules most often broken in edits: no wildcard imports; braces on every block; `@Override` wherever legal; `UPPER_SNAKE_CASE` constants; uppercase `L` on long literals; 100-column lines.

**Javadoc on every visible member** except the simple and obvious ones (the guide's section 7). It is the contract, not decoration: `@param`, `@return` and `@throws` state what a caller may rely on, editors show it at the call site, and an agent reading a class learns its contract without reading its body. A summary line alone is enough only where the guide allows it.

## 8 Anti-Patterns

- **Logic in the Activity:** testable only on a device (1.1).
- **A bounded wait on the main thread:** "only 2 seconds" per call, several calls per event (2.1).
- **A cast as a range check** (3.2).
- **Timestamps from two clocks subtracted** (4.2).
- **Building with whatever JDK is installed** (6.1).
- **A wire format copied into each code base without a shared contract** (3.1).

## 9 Amendment

Amend this policy when a rule here is shown wrong by a measured failure, stating the failure generically in the rule's section.
