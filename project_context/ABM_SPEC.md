**ABM 2.0: ABSOLUTE MASTER TECHNICAL SPECIFICATION**

**System Nature: Local-First Personal Cognitive OS & Strategic Twin**

**Target Build Track: Phase v0.1 Core Initialization**

**1. STRATEGIC SCOPE & BOUNDARY GUARDRAILS**

-   **Core Mandate:** ABM 2.0 is an absolute privacy-isolated,
    local-first **Cognitive Operating System** designed to function as a
    persistent digital twin of the developer Araba (ABM). It replicates
    personal technical reasoning, architectural preferences, and
    decision-making patterns without hallucination.

-   **The Corporate Boundary:** ABM 2.0 acts strictly as an
    administrative overseer, high-level strategic advisor, and
    engineering supervisor for your company, **First Minds Proprietary
    Limited**. It is architecturally decoupled from future
    consumer-facing operational systems.

    -   **Inside ABM 2.0:** Strategic planning, code style matching,
        project resource analysis, engineering oversight, and decision
        logging.

    -   **Excluded (Built Separately Later in FirstMinds Corporate
        OS):** Consumer CRM, active client invoice databases, scheduling
        portals, public-facing applications, and live billing pipelines.
        ABM 2.0 sits *above* these systems to help you design and manage
        them.

**2. SYSTEM ARCHITECTURE & DECOUPLED INFRASTRUCTURE**

-   **Desktop Daemon:** Runs as a continuous, non-blocking background
    system service independent of any single IDE. It tracks file-system
    event streams using native kernel hooks (inotify /
    ReadDirectoryChangesW) and maps inference directly through local
    loopback requests (127.0.0.1:11434) to an Ollama server instance.

-   **Mobile Twin Node:** Runs as a permanent Android Foreground Service
    on a **Tecno Spark 40** hardware framework, locked into system
    memory with an ongoing notification flag to completely bypass OS
    low-memory garbage collection thread kills.

-   **Cross-Node State Synchronization:** When the Desktop Daemon and
    the Tecno Spark 40 occupy the same local network (LAN), state data,
    clipboards, and session context switch over an authenticated local
    WebSocket transport layer. Upon dissociation, the system switches
    automatically to an end-to-end encrypted remote relay network
    channel to preserve state.

-   **Asynchronous Event Bus:** Internal component communication is
    fully decoupled. Direct dependencies between modules are banned. All
    system events (e.g., CODE_CHANGED, CONTEXT_STREAM_QUARANTINED,
    HARDWARE_SHIFT_DETECTED) are broadcast across a centralized local
    Event Bus, allowing modules to listen and react asynchronously
    without blocking execution threads.

**3. QUAD-STREAM HIGH-DENSITY MEMORY ARCHITECTURE**

Data segmentation is strictly handled locally across four distinct
vector database collections managed via ChromaDB. Data crossover or
inter-collection bleed is blocked by process separation rules:

\[ EXECUTIVE ORCHESTRATOR \]

│

┌───────────────┬──────┴────────┬───────────────┐

▼ ▼ ▼ ▼

Stream D Stream A Stream B Stream C

(abm_cognitive\_ (abm_code\_ (abm_technical\_ (abm_ambient\_

identity) topologies) mastery) telemetry)

1.  **Stream D (Collection: abm_cognitive_identity)**

    -   *Purpose:* Identity foundations, personal/professional goals,
        and FirstMinds corporate philosophies. It dictates *why*
        decisions are made.

    -   *Data Format:* Document-style raw text matrices defining
        operational strategies, target objectives, and corporate
        philosophies.

    -   *Metadata Schema:* {\"owner\": \"ABM\", \"target_entity\":
        \"FirstMinds\", \"volatility\": \"immutable\"}

2.  **Stream A (Collection: abm_code_topologies)**

    -   *Purpose:* Houses your personal engineering DNA, formatting
        signatures, and pattern designs.

    -   *Chunking Strategy:* Structural code chunking. The ingestion
        engine parses files strictly by Abstract Syntax Tree (AST) node
        clusters, class boundaries, or closing bracket parameters. Code
        is never split mid-line.

    -   *Technical Competencies:* Deep structural style-matching for
        Python, Java, JavaScript, CSS, HTML, and Kotlin. Core
        architecture style matching targets cross-platform applications
        built via **Dart and the Flutter framework** using the **BLoC
        (Business Logic Component)** state management pattern.

    -   *Metadata Schema:* {\"language\": \"dart\|kotlin\|python\",
        \"framework\": \"flutter\", \"state_pattern\": \"bloc\",
        \"naming_convention\": \"camelCase\"}

3.  **Stream B (Collection: abm_technical_mastery)**

    -   *Purpose:* Retains validated technical assets, documentation
        dumps, verified API references, and external package schemas.

    -   *Chunking Strategy:* Recursive token chunking (500-token window
        size with a 50-token recursive overlap window).

    -   *Metadata Schema:* {\"source\":
        \"duckduckgo_sandbox\|docs_fetch\", \"date_acquired\":
        \"2026-07-18\", \"confidence_score\": \"0.92\"}

4.  **Stream C (Collection: abm_ambient_telemetry)**

    -   *Purpose:* Chronological interaction history logs, terminal
        input/output sequences, clipboard deltas, and voice notes.

    -   *Chunking Strategy:* Chronological windowing. Time-slice
        clustering groups events together, splitting blocks when an
        absolute 120-second pause in system interaction occurs.

    -   *Rollout Phase Guardrail:* To protect privacy and prevent data
        noise, ingestion starts strictly with Git trees, IDE workspaces,
        and static design documents. Clipboard tracking, voice logs, and
        browser tracking are kept offline until core memory systems are
        fully stable.

    -   *Metadata Schema:* {\"epoch_timestamp\": 1784370192,
        \"active_repository\": \"smart_transit\|houseconnect\",
        \"device_source\": \"tecno_spark_40\"}

**4. MODEL AGNOSTIC CHANNELS & ROLE SEPARATION**

Models are entirely abstracted behind rigid protocol wrappers
(PlanningModelInterface, CodingModelInterface), allowing you to hot-swap
local models down the line without modifying core orchestration logic.
Tasks are processed across specialized local model allocations via
Ollama:

-   **Intent Routing & Classification Node:** Executed via phi3:mini (or
    ultra-lightweight SLM equivalents) to perform lightning-fast input
    tagging, routing, and classification passes.

-   **Strategic Planning & Architecture Engine:** Executed via
    llama3:8b-instruct to orchestrate high-level layouts, system
    summaries, and multi-layered dependency evaluations.

-   **Code Synthesis & Refactoring Specialist:** Routed through an
    optimized local code generation specialist (e.g., deepseek-coder or
    qwen-coder) for functional clean-code output.

-   **Vectorization Generation Processing:** Managed by a standalone
    embedding model (e.g., nomic-embed-text) to guarantee mathematical
    vector consistency across all memory indexing operations.

**5. NON-GENERATING EXECUTIVE ORCHESTRATOR & TASK CONTRACTS**

The central orchestrator acts as a micro-kernel router. It is
programmatically banned from generating any raw code or text
explanations directly. Instead, it enforces a strict operational
processing loop powered by immutable **Task Contracts**:

\[Input Received\] ──\> \[phi3 Classifies\] ──\> \[Generate Task
Contract\]

│

▼

\[Execute in Sandbox\] \<── \[Verify Permissions\] \<── \[Retrieve
Vectors\]

│

▼

\[Multi-Factor Gate\] ──\> \[Passed\] ──\> \[Commit / Output\]

│

└──\> \[Failed\] ──\> \[Quarantine Queue\]

**The Task Contract Format**

Before any sub-agent is allowed to initialize a task, the Orchestrator
outputs a structured contract layout:

JSON

{

\"contract_id\": \"TXN_784370192\",

\"objective\": \"Build secure local token encryption module\",

\"department\": \"software_engineering\",

\"assigned_agents\": \[\"architecture_node\", \"code_specialist\"\],

\"autonomy_permission_level\": 2,

\"hard_success_conditions\": \[

\"syntax_tree_validity == true\",

\"security_vulnerability_scan == clean\",

\"unit_test_compilation == success\"

\]

}

*If a sub-agent attempts to perform an action outside of its assigned
contract boundaries (e.g., attempting a Level 3 write to disk while
under a Level 2 Sandbox restriction), the Orchestrator executes an
immediate, hard thread termination.*

**6. MATHEMATICAL GOVERNANCE & MANDATORY FLOOR GATES**

To prevent style-matching hallucinations or faulty code additions from
corrupting memory layers, incoming data packages or code additions must
pass a multi-factor confidence verification equation. Let Confidence
($C$) represent the weighted sum of five operational variables:

$$C = 0.30\left( M_{align} \right) + 0.25\left( T_{correct} \right) + 0.20\left( S_{val} \right) + 0.15\left( Test_{succ} \right) + 0.10\left( P_{align} \right)$$

-   $M_{align}$ **(Memory Alignment):** Vector cosine similarity match
    against historical developer style guidelines stored in Stream A.

-   $T_{correct}$ **(Technical Syntax Validation):** Abstract Syntax
    Tree (AST) validation verifying syntax correctness for the targeted
    language.

-   $S_{val}$ **(Security Verification):** Static code analysis
    validation score ensuring zero plain-text secrets or insecure
    dependencies.

-   $Test_{succ}$ **(Isolated Test Success):** Build performance metrics
    achieved inside the isolated background sandbox environment.

-   $P_{align}$ **(Preference Alignment):** Rule-based compliance
    confirmation matching the architectural constraints in Stream D.

**Absolute Floor Gates**

An ingestion task or code integration passes automatically if and only
if $C \geq 0.85$. However, some values can never compensate for others.
A high style match cannot mask broken or insecure code. The system
triggers an **absolute intercept** if any of these floor parameters are
breached:

-   $S_{val}$ **(Security Validation) MUST be** $\geq 0.80$ (Absolute
    block if security errors occur).

-   $Test_{succ}$ **(Sandbox Build Success) MUST be** $\geq 0.90$
    (Absolute block if code fails to compile).

*Any package that fails the Confidence Threshold or breaches a Hard
Floor Gate is blocked from updating permanent memory and moved to the
isolated **Ambiguity Queue** directory (./memory/ambiguity_quarantine/),
triggering a system notification for manual human intervention.*

**7. PHYSICAL WORKSPACE RUNTIME AUTONOMY LEVELS**

System interaction boundaries are locked behind five sequential security
validation rings:

-   **Level -1 (Simulation Mode):** Synthetic playground environment
    testing. System behaviors are simulated completely offline before
    touching or monitoring actual user directories.

-   **Level 0 (Observe Only):** Absolute read-only execution. The system
    logs user event states to Stream C but cannot touch files or execute
    console scripts.

-   **Level 1 (Suggestive Proposals):** System builds isolated
    suggestion patch documents (.patch or markdown previews). It has no
    write access to production workspace paths.

-   **Level 2 (Sandbox Simulation):** System clones project components
    into an isolated **Docker container sandbox**. It runs builds,
    executes platform compilers, and performs unit testing within the
    container to track compilation profiles. It is completely blocked
    from modifying live files on the host drive.

-   **Level 3 (Controlled Modification):** System applies build-verified
    patches directly to the physical storage drive, restricted
    exclusively to staging or feature-specific Git branch structures.
    Direct main branch commits are blocked.

-   **Level 4 (Autonomous Operation):** Full programmatic read/write
    deployment capabilities across pre-approved, non-critical local
    workspace paths.

**8. HARDWARE COMPUTE SHUNTS & REFLECTION LOOPS**

-   **Compute Shunt Throttle:** The desktop daemon monitors host
    resource metrics continuously. If total CPU utilization breaches
    65%, or GPU utilization spikes above 50% (such as during active
    project compilations or intensive PC gaming sessions), the compute
    shunt activates immediately. Deep vector calculations, semantic
    searches, and model inference passes freeze. Incoming telemetry data
    appends into an unindexed flat-file cache on disk to prevent UI
    stuttering or game lag.

-   **Analysis Ingestion Mode:** When host compute resource consumption
    drops below 20% consistently for more than 180 seconds, Analysis
    Mode activates. The daemon reads the flat-file cache sequentially,
    calculates text embeddings, updates vector indexes, and optimizes
    database graphs seamlessly.

-   **Daily Reflection Loop:** Every 24 hours during deep idle cycles,
    the Reflection module aggregates the raw data dumps in Stream C. It
    runs a local synthesis pass to extract core developer lessons,
    updates the behavioral logs in Stream D, and purges the messy raw
    text dumps to keep database retrieval times incredibly low.

**9. HUMAN-TWIN EMULATION & INTERFACE LAYER**

-   **Cognitive Resonation:** To ensure the system feels like a natural
    human extension of yourself while maintaining absolute control, the
    *Persona Injection Customizer* utilizes a specialized **Reflection
    Loop**. When summarizing strategic choices or technical trade-offs,
    ABM 2.0 uses your personal problem-solving lens (retrieved from
    Stream D)---balancing rapid implementation velocity for MVPs with
    high-fidelity clean-code conventions for core architectures.

-   **Dual-Voice Paradigm:** The system speaks to you with a
    collaborative, peer-to-peer tone (acting like a brilliant
    co-architect pitching options to a founder), but uses cold, silent,
    non-generating JSON contracts for all backend agent processing. You
    remain in complete, uncompromised control.

**10. STEP-BY-STEP WORKSPACE IMPLEMENTATION PATHWAY**

Coding agents must build the system following this strict development
progression, verifying each phase reaches 100% test validation before
initializing the next:

1.  **Phase v0.1 (Memory Brain Core):** Initialize ChromaDB, configure
    the database collections for Streams A, B, C, and D, set up the
    standalone local embedding model connector, and build script tests
    with mock assertions to prove data isolation works perfectly.

2.  **Phase v0.2 (Developer Companion Node):** Build IDE file-watcher
    hooks, local Git integration pipelines, Abstract Syntax Tree parsing
    tools, and the style fingerprint extraction engine.

3.  **Phase v0.3 (Executive Orchestrator Engine):** Deploy the
    non-generating classification router node, define the sub-agent
    department worker sandboxes, and map JSON task delegation schemas.

4.  **Phase v0.4 (Safe Action Sandbox):** Deploy background Docker
    container initialization routines, inject compiler testing check
    loops, and implement the multi-factor validation gate formula.

5.  **Phase v0.5 (FirstMinds Strategic Wing):** Build internal decision
    tracking journals, workflow overview monitors, and strategic asset
    analyzers to map out architecture paths for your company.

6.  **Phase v1.0 (Cognitive OS Release):** Spin up the Android
    Foreground Service for the Tecno Spark 40, activate the encrypted
    cross-node synchronization channel, and deploy ambient interaction
    managers

**🔧 THE HARDWARE-AGNOSTIC BLUEPRINT CORRECTIONS**

-   **Section 2: Mobile Twin Node Architecture (Updated)**

    -   *Old Framework:* Hardcoded Tecno Spark 40 execution.

    -   *New Architecture:* Deployed as a highly modular, universal
        **Android Foreground Service** optimized for modern
        high-performance devices (like your Redmi Note 14 Pro or future
        upgrades). It relies on standard Android API hooks rather than
        device-specific binaries, utilizing a persistent notification
        flag to prevent the host OS\'s low-memory killer from stripping
        its execution thread.

-   **Section 3 & Section 9: Telemetry Metadata (Updated)**

    -   The metadata property schema for Stream C shifts from a rigid
        string to a dynamic device variable:

    -   {\"epoch_timestamp\": 1784370192, \"active_repository\":
        \"smart_transit\", \"device_source\": \"dynamic_mobile_node\"}
