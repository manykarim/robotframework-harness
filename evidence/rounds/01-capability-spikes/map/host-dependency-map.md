# rf-mcp host-dependency map

**What I analysed:** repo `~/workspace/rf-mcp-robotcode`, branch `research/robotcode-remote-mcp` @ `c1a18eb` (v0.36.0). I made no changes.

**How refs are written:** every `file:line` below is relative to `~/workspace/rf-mcp-robotcode/src/robotmcp/`. The absolute paths of the key files are listed in section 8.

**Three facts that shape everything else:**

1. **Three of the requested components are not on this branch.** `PostActionVerifier`, `WrapperSuggester` and the web `actionable_elements`/`actionable_surface` exist only on branch `feature/improve_complex_sites_handling` (`9d4ad5c`), in `components/execution/post_action_verifier.py`, `wrapper_suggester.py` and `page_source_service.py` (`ActionableElementsCollector`). I analysed them with `git show`. This branch only has the desktop `actionable_controls` (`components/execution/ui_tree_service.py:808`).
2. **robotcode 2.7.0 is installed at `~/workspace/rf-mcp-robotcode/.venv/bin/robotcode`.** I read its repl-server protocol directly:
   - RPC methods: `initialize`, `executeCell(source, language_id)`, `interrupt`, `shutdown`, `exit` (`robotcode/repl_server/protocol.py`).
   - `executeCell` returns `{success, items:[{mime:"x-application/robotframework-repl-log", data:<JSON tree>}, stderr?]}`.
   - The JSON tree nodes are keyword results with name, owner (the resolving library), args, assign, status, message and times. Child log messages include RF's `${var} = value` assignment lines (`interpreter.py`).
   - **There is no robotcode CLI client for repl-server.** Keeping a live browser across the agent's separate shell calls needs a long-lived `robotcode repl-server --tcp` plus a small JSON-RPC client. Otherwise every call must replay the whole script via `robotcode repl --plain FILES` or `robotcode robot`.
   - `robotcode --format json` works for `results *` and `analyze code`. There is also a root `--wrapper "xvfb-run -a"` option.
3. **The whole server is built around one live RF process.** Section 1 lists the details.

---

## 1. Cross-cutting host facts

| # | Fact | Evidence |
|---|---|---|
| 1 | **One RF execution context for the whole process.** `create_context_for_session` reuses `EXECUTION_CONTEXTS.current` if one exists, so every session shares one Namespace and VariableScopes. The session's search order is re-applied before every keyword. All keyword execution is serialized by one asyncio lock. | `components/execution/rf_native_context_manager.py:133-253, 560-576`; `components/execution/keyword_executor.py:339, 1913` |
| 2 | **Two separate sets of library instances live in the server process.** (a) `LibraryManager.try_import_library` instantiates `Browser()`, `SeleniumLibrary()`, `RequestsLibrary()` etc. directly. This is triggered by `ExecutionSession.import_library` → `_ensure_library_loaded_immediately`, i.e. by init, analyze and recommend. (b) Imports into the live RF Namespace. | `core/library_manager.py:179-330, 418-490`; `models/session_models.py:299-445`; `rf_native_context_manager.py:267-325` |
| 3 | **Keyword discovery reflects the server's installed packages, not the user's.** `RobotFrameworkDocStorage` runs `LibraryDocumentation` over registry libraries importable on the server (`find_spec` gate). "Project sources" are libdoc-parsed from paths on the server filesystem. `KeywordMatcher` builds its own libdoc registry. | `utils/rf_libdoc_integration.py:115-190, 644-760`; `components/keyword_matcher.py:429-520` |
| 4 | **The server writes to its own filesystem by default.** | See list below |
| 5 | **Most state lives in process-global singletons.** | See list below |
| 6 | **Sessions of different users would leak into each other on a shared server.** | See list below |
| 7 | **Attach-mode steps are never recorded.** The `execute_step` bridge branch returns before any `add_step`, and `start_test`/`end_test` are refused when a bridge is active. So `build_test_suite` cannot see bridge-executed steps. | `server.py:4834-4888, 3984, 4093` |
| 8 | **Timeouts are not enforced by wall clock.** A per-session timeout policy is computed, but it is only injected as `timeout=` into Browser/Selenium wait keywords. | `keyword_executor.py:2556-2582, 3387-3548` |

**Filesystem writes (row 4):**
- Artifacts in `./.robotmcp_artifacts`. Mode defaults to `auto` with a 500-token threshold, and responses say "Content saved to {file_path}" — a server path the client cannot read. `fetch_artifact` is off by default. `domains/artifact_output/value_objects.py:92-143`
- Instruction learning in `~/.rf-mcp/instruction_learning` and `~/.rf-mcp/patterns`. On by default; disable with `ROBOTMCP_DISABLE_LEARNING`. `optimization/instruction_hooks.py:135`, `optimization/pattern_store.py:40`
- Memory DB `~/.rf-mcp/memory.db`, opt-in. `domains/memory/value_objects.py:664-703`
- RF output temp dirs `rf_mcp_*`. `rf_native_context_manager.py:177`
- Screenshots, suite-run temp dirs, `build_test_suite(output_path)`, and the PlatynUI held-keys state file.

**Process-global singletons (row 5):**
- Engine and session manager: `server.py:1321-1365`
- `nlp_processor`, `keyword_matcher`, `library_recommender`, `state_manager`: `server.py:1307-1311`
- Service container — timeout policies, `batch_state_manager`, `delta_state_service`, artifact store: `container.py:63-230`
- Intent/profile singletons: `server.py:75-80`
- Libdoc store, plugin manager, memory hook service, instruction hooks, frontend `event_bus`.

**Cross-session leakage (row 6):**
- `SessionResolver` falls back to "the most recently active session with steps" for build, run and validation. `utils/session_resolution.py:17-73, 153`
- `intent_action` infers the session from *all* sessions in the process. `domains/intent/weak_model_guards.py:144-213`
- Tool profiles change tool visibility globally. `server.py:302-309, 4251-4289`

---

## 2. Public tools: per-tool map

**Column key for all tool tables:**
- **Host deps** — needs a live RF context/namespace, live library instances, DOM/screens, the local filesystem, installed packages/libdoc, spawned processes, or network.
- **State** — which in-memory server state the tool reads or writes.
- **Pure (remote-able)** — logic that could run on a remote server given text inputs.
- **robotcode** — the client-side primitive that could replace the host part.

### analyze_scenario — `server.py:2161-2446`
| Aspect | Detail |
|---|---|
| Purpose / params | The "front door": NLP analysis of a scenario, then create and auto-configure a session. Params: `scenario`, `context` (web/mobile/api/desktop), `session_id`, `ctx` (for LLM sampling). |
| Host deps | `session.configure_from_scenario` → `_apply_session_configuration` → `import_library(pref, force)` → `LibraryManager.load_library_on_demand`, which instantiates the library in the server and needs the package installed (`session_models.py:961-1033`). The mobile path uses `initialize_mobile_session` (`session_manager.py:359`). If `ROBOTMCP_ATTACH_HOST` is set, it calls the attach bridge over HTTP (`diagnostics`, `get_variables`; `server.py:2271-2307`). Optional MCP sampling `ctx.sample` goes back to the client's LLM. |
| State | Writes a new `ExecutionSession` (uuid id): `scenario_text`, `explicit_library_preference`, `preference_source`, `session_type`, `platform_type`, `search_order`, `imported_libraries`, `loaded_libraries`, `auto_configured`, `mobile_config`. Also instruction-hooks `on_session_start` and memory recall/augment. |
| Pure (remote-able) | `nlp_processor.analyze_scenario` (`components/nlp_processor.py:202`), `detect_platform_from_scenario` (`session_manager.py:287`), explicit-preference and session-type detection (`session_models.py:666-960`), search-order profiles (`session_models.py:1136-1242`), `build_api_init_guidance` (`utils/requests_guidance.py`). |
| robotcode | Pure part needs nothing. Library presence: `robotcode libdoc <Lib> version` exit code, or `robotcode discover info`. |

### recommend_libraries — `server.py:1795-2158`
| Aspect | Detail |
|---|---|
| Purpose / params | Rank libraries for a scenario, optionally applying them to a session. Params: `scenario`, `context`, `session_id`, `max_recommendations`, `check_availability`, `apply_search_order`, `mode` (direct / sampling_prompt / merge_samples), `samples`, `k`, `available_libraries`, `include_keywords`, `use_llm_refinement`. |
| Host deps | **Availability:** `check_library_requirements` → `check_and_suggest_libraries` → `importlib.import_module` in the server, plus orchestrator and BrowserLibraryManager status (`execution_coordinator.py:290-388`, `utils/library_checker.py:17-66, 151`). **With a session:** `session.import_library(force)` (server-side instantiation) and `rf_mgr.import_library_for_session` (live Namespace) (`server.py:1999-2034`). **Keyword list:** the libdoc cache is used when plugin hints are missing (`server.py:1912-1951`). |
| State | Reads `explicit_library_preference`. Writes `imported_libraries` and `search_order`. |
| Pure (remote-able) | `LibraryRecommender.recommend_libraries` over the static plugin registry (`library_recommender.py:122-230`); sampling/merge prompt builders (`server.py:1230-1303`); Browser/Selenium conflict filtering; LLM refinement (`server.py:1713-1792`); RequestsLibrary hint. |
| robotcode | `robotcode libdoc <Lib> version` / `list` (availability, keyword names). The auto-import becomes an `Import Library` line sent through `executeCell`. |

### check_library_availability — `server.py:5454-5509`
| Aspect | Detail |
|---|---|
| Purpose / params | Check whether libraries are importable or installable. Param: `libraries`. |
| Host deps | For path-like entries: `os.path.exists` + `robot.libdoc.LibraryDocumentation(path)`. For names: `check_library_requirements` (importlib in the server). A `pip show` subprocess helper exists (`library_checker.py:97`) but the main path uses importlib. |
| State | None. |
| Pure (remote-able) | Only the install-suggestion text from the registry (`config/library_registry.py:249`). |
| robotcode | `robotcode libdoc <name\|path> version` exit status; `robotcode --format json analyze code` (unresolved imports); `robotcode discover info` (RF/Python versions). |

### execute_step — `server.py:4662-5026`, core in `keyword_executor.py:1869-3113`
Params: `keyword`, `arguments`, `session_id`, `raise_on_failure`, `detail_level`, `scenario_hint`, `assign_to`, `use_context`, `mode` (keyword/evaluate), `expression`, `timeout_ms`, `bdd_group`, `bdd_intent`, `record`, `pre_validate_timeout_ms`.

| Stage | Where | Host or pure |
|---|---|---|
| Coerce args to strings, strip BDD prefix, rewrite evaluate mode | `server.py:4771-4825` | Pure |
| Attach routing (`_compute_effective_use_context` calls bridge `diagnostics`; `run_keyword` over HTTP). **Not recorded.** | `server.py:953-988, 4827-4888` | Network |
| Library-preference check via static plugin keyword map | `server.py:4890-4922`; `plugins/manager.py:173, 239` | Pure |
| Auto-load session libraries | `execution_coordinator.py:207-271` | Host (instances) |
| Locator conversion (off by default) | `execution_coordinator.py:443-506` | Pure |
| Desktop guards: X11 env, safety guard (display classification via env and `/proc`), focus-before-act (PlatynUI runtime), executable resolution, snap sanitize, CharacterCount probes | `keyword_executor.py:2089-2273` | Host (native desktop) |
| Library registration + plugin `before_keyword_execution` | `keyword_executor.py:3217-3286` | Host |
| Pre-validation (section 3) | `keyword_executor.py:2375-2553` | Decision pure; probe host |
| Timeout policy and injection (section 3) | `keyword_executor.py:2556-2568, 3387` | Pure given the owner library |
| Plugin override (e.g. rejecting Open Browser — pure; Drag-and-Drop pre-scroll — live) | `keyword_executor.py:3860-3879`; `plugins/builtin/browser_plugin.py:370-501` | Mixed |
| Create context / import libraries / sync search order; push `session.variables` into RF Variables; run keyword in a worker thread | `keyword_executor.py:3892-4017`; `rf_native_context_manager.py:423-595` | **Host (live RF context)** |
| Resolve owner library via `namespace.get_runner` → `resolved_library`, and `qualified_keyword` when ambiguous | `keyword_executor.py:4026-4062` | Host (repl `owner` gives the same) |
| Update `browser_state` from the owner library (active_library, url, page source) | `keyword_executor.py:4064-4111` | Host |
| Record gate `_resolve_record_gate` → `session.add_step` | `keyword_executor.py:93-134, 2637-2660` | Pure |
| Desktop post-signals: close/launch liveness (`os.kill`, `Popen.poll`, `os.getsid`), evidence, Wayland warning, steering confidence (can flip success to failure), tree-cache refresh | `keyword_executor.py:2662-2925` | Host |
| Variable assignment (raw objects into `session.variables`; `step.assigned_variables`) | `keyword_executor.py:2940-3005, 3115` | Pure given the value |
| Hints and response shaping | `keyword_executor.py:4718-4919`, `3077-3113` | Pure |
| Memory augment, deprecation alias, `ToolError`, externalize, learning | `server.py:4938-5024` | Pure (text), but externalization writes to the server filesystem |

- **State written:** `steps` / `test_registry.current.steps` / `suite_level_steps`, `variables` (raw Python objects), `executed_step_count`, `failed_step_count`, `browser_state`, `last_activity`, BDD annotations on the last step, desktop flags, pid/sid and `_platynui_*` fields. Also the RF context Variables, timeout policy, memory, learning, artifacts and event bus.
- **robotcode:** `executeCell("${x}=    Keyword    a    b")` against a long-lived repl-server. `owner` gives `resolved_library`; `status`/`message` give the error; messages give assignment values; `Set Library Search Order` covers search order. Without a persistent server, the whole script is replayed each call.

### execute_batch / resume_batch — `server.py:5661-5778`, `5781-5921`
| Aspect | Detail |
|---|---|
| Purpose / params | Run N steps with `${STEP_N}` chaining, a failure policy and resume. `execute_batch`: `session_id`, `steps`, `on_failure` (stop/retry/recover), `max_recovery_attempts`, `timeout_ms`. `resume_batch`: `batch_id`, `fix_steps`, `timeout_ms`. |
| Host deps | Each step goes through `engine.execute_step` (`adapters/recovery_adapter.py:196-230`). Tier-1 recovery runs keywords (wait/scroll/dismiss); tier-2 captures page state (Take Screenshot / Get Page Source / Get Url / Get Title) (`adapters/page_state_adapter.py:14-100`). Failure evidence is a base64 screenshot. Desktop retry gating inspects the PlatynUI BareMetal instance (`recovery_adapter.py:84-150`). |
| State | `BatchStateManager`, in memory with a 300 s TTL (`domains/batch_execution/services.py:322-367`). It holds `BatchState` (batch id, session id, failed step, remaining steps, results, raw `results_map`, policy, remaining timeout) (`domains/batch_execution/aggregates.py:421-517`). Steps are also recorded into `session.steps`. |
| Pure (remote-able) | `StepVariableResolver` (`services.py:55-107`), batch aggregate and validation, the `ErrorClassifier` and strategy selection (`domains/recovery/services.py:55-120`), the digest. |
| robotcode | One multi-line cell through `executeCell` (RF chains `${x}=` natively; recovery via `TRY` or `Wait Until Keyword Succeeds`). Or a temp `.robot` file + `robotcode robot` + `robotcode --format json results log`. Resume state goes into a client file. |

### execute_flow — `server.py:4310-4384`; implementations `6009-6213`, `5588`
| Aspect | Detail |
|---|---|
| Purpose / params | if / for-each / try execution. Params: `structure`, `session_id`, `condition`, `then_steps`, `else_steps`, `items`, `item_var`, `stop_on_failure`, `max_iterations`, `try_steps`, `except_patterns`, `except_steps`, `finally_steps`, `rethrow`. |
| Host deps | Condition runs as `Evaluate` in the RF context. Steps run through `engine.execute_step`. For-each sets the loop variable with `Set Test Variable`. |
| State | Writes a `flow_blocks` AST to the session or current test; inner steps are also recorded. |
| Pure (remote-able) | Block recording, step normalization, except-pattern matching (`fnmatch` on error text). |
| robotcode | `executeCell` with native RF `IF` / `FOR` / `TRY` blocks. |

### find_keywords — `server.py:2703-3345`; helpers `423-616`, `2449-2700`
| Aspect | Detail |
|---|---|
| Purpose / params | Keyword discovery. Params: `query`, `strategy` (semantic / pattern / catalog / session), `context`, `session_id`, `library_name`, `current_state`, `limit`, `strict_library`. |
| Host deps | **semantic:** `keyword_matcher.discover_keywords` over a libdoc registry of server-installed libraries, plus optional model2vec embeddings when `ROBOTMCP_SEMANTIC_KEYWORDS` is set. **pattern / catalog:** `_ensure_all_session_libraries_loaded` (instantiates libraries) + libdoc store search (`execution_coordinator.py:895-1027`). **session:** live namespace via `rf_mgr.list_available_keywords` (`rf_native_context_manager.py:1646`). **Project keywords:** libdoc of files on the server filesystem. |
| State | Reads `explicit_library_preference`, `imported_libraries`. Writes artifacts, learning, memory. |
| Pure (remote-able) | BDD strip, empty-query guard, preference precedence, `_filter_keywords_by_session_library` (plugin incompatibility tables), confidence cap/rerank, recommendation rebuild, project scoring (`server.py:423-519`), catalog hard cap, embedded-arg annotation. |
| robotcode | `robotcode libdoc <Lib\|resource/py path> spec.json` per imported library, done on the client. The server ranks over the supplied specs. There is no "list namespace keywords" primitive; use libdoc on each import. |

### get_keyword_info — `server.py:6271-6394`; helpers `6397-6666`
| Aspect | Detail |
|---|---|
| Purpose / params | Documentation or signature parsing. Params: `mode` (keyword / library / session / parse), `keyword_name`, `library_name`, `session_id`, `arguments`. |
| Host deps | **keyword / library:** libdoc store + project store (`execution_coordinator.py:1043-1445`). **session:** live namespace `get_keyword_documentation` (`rf_native_context_manager.py:1741`) or the bridge. **parse:** `ArgumentProcessor.parse_arguments_for_keyword`, using discovered signatures and `session.variables`. |
| State | Reads `imported_libraries`, `explicit_library_preference`, `variables`. |
| Pure (remote-able) | Session scoping (imported + neutral libraries), the library-mismatch hint via plugin `validate_keyword_for_session`, externalization gating. |
| robotcode | `robotcode libdoc <Lib> show "<Kw>"` or a JSON spec. Parse becomes pure given the spec arguments. |

### get_locator_guidance — `server.py:7154-7237`
| Aspect | Detail |
|---|---|
| Purpose / params | Locator / RequestsLibrary / visual guidance. Params: `library`, `error_message`, `keyword_name`. |
| Host deps | None. The `RobotFrameworkNativeConverter()` constructor touches `get_rf_doc_storage()` lazily without initializing it. It needs the `robot` package importable, nothing live. |
| State | None. |
| Pure (remote-able) | **100%** (`utils/rf_native_type_converter.py:1267-1720`, `utils/requests_guidance.py`, `utils/visual_guidance.py`). |
| robotcode | Not needed. |

### get_session_state — `server.py:4387-4659`
Params: `session_id`, `sections`, `state_type`, `elements_of_interest`, `page_source_filtered`, `page_source_filtering_level`, `include_reduced_dom`, `include_dom_stream`, `dom_chunk_size`, `mode` (full/delta/auto/none), `since_version`.

| Section | Implementation | Host dependency | robotcode replacement |
|---|---|---|---|
| summary | `_get_session_info_payload` (`server.py:7084-7145`) | Server state only (+ bridge diagnostics) | Client state file |
| application_state | `state_manager.get_state` (`components/state_manager.py:84`); DOM via page source; api/db largely simulated | Live | `executeCell` running Get Page Source / Get Url / Get Title |
| page_source | `PageSourceService.get_page_source` (`page_source_service.py:358`): Get Page Source / Get Source in the RF context (`72-181`), Browser aria snapshot (`478-557`), Appium source (`807-1052`); `filter_page_source` (`225`) is pure over HTML | Live library + DOM | `executeCell("${s}= Get Page Source")` or `Get Aria Snapshot`; the server filters the text |
| variables | Live RF Variables store → fallback `session.variables` (`server.py:6957-7075`) | Live context | `executeCell("Log Variables")` |
| validation | `get_session_validation_status` (`execution_coordinator.py:1612`) | None | Client state |
| libraries | LibraryManager/libdoc status + project sources (`server.py:7460-7478, 4509-4535`) | Installed packages | `robotcode libdoc` / `discover info` |
| rf_context | Live namespace and context info (`server.py:7711-7747`) | Live context | Not applicable (the repl-server process is the context) |
| ui_tree (auto-added for desktop) + desktop_environment | `get_ui_tree` (`ui_tree_service.py:480`), native PlatynUI runtime; `get_desktop_environment` (`561`) reads `DISPLAY` and `/proc` | Native desktop | Partial: PlatynUI Query keywords via `executeCell`; there is no bounded tree-dump command |
| actionable_controls | `ui_tree_service.py:808` | Native desktop | Same as ui_tree |
| delta mode | `DeltaStateService`, a server-side versioned cache (`domains/snapshot/delta_service.py:20`) | None | Client-side diff |

Also memory augment, externalization and learning.

### intent_action — `server.py:8015-8394`
| Aspect | Detail |
|---|---|
| Purpose / params | High-level verb mapped to a library keyword. Params: `intent`, `target`, `value`, `session_id`, `options`, `assign_to`, `detail_level`, `force`, `match`, `nth`, `commit`, `mode`, `attribute_name`. |
| Host deps | Execution through `execute_step`. `commit` adds a `Dispatch Event`. The navigate fallback steps are executed. |
| State | Reads **all** sessions for session inference; reads `imported_libraries`. |
| Pure (remote-able) | `IntentResolver.resolve` (`domains/intent/services.py:106`); `SessionLookupAdapter` (imported libraries → web library / platform) (`domains/intent/adapters/session_lookup_adapter.py`); `LocatorNormalizerAdapter`; `IntentRegistry.with_builtins` (`domains/intent/aggregates.py:140`); nth/match/force/extract handling (`adapters/mcp_tool.py:16-206`); guards (`weak_model_guards.py:105-213`); `get_navigate_fallback` (`services.py:221`). |
| robotcode | The server returns the resolved RF line; the agent runs it with `executeCell`. |

### manage_attach — `server.py:7759-7953`
| Aspect | Detail |
|---|---|
| Purpose / params | Status/control of the McpAttach bridge. Param: `action` (status / stop / cleanup / reset / disconnect_all). |
| Host deps | HTTP to `ROBOTMCP_ATTACH_HOST:PORT` with the token header (`components/execution/external_rf_client.py`). |
| State | `cleanup_expired_sessions` / `cleanup_all_sessions`. |
| Pure (remote-able) | Health classification (`server.py:1133-1226`). |
| robotcode | The agent's shell manages `robotcode repl-server` / `robot-debug` process lifecycle. |

### manage_library_plugins — `server.py:1636-1710`
| Aspect | Detail |
|---|---|
| Purpose / params | Plugin list / reload / diagnose. Params: `action`, `plugin_name`. |
| Host deps | `importlib.metadata` entry points from the server's site-packages, and JSON manifests from `ROBOTMCP_PLUGIN_PATHS` or `.robotmcp/plugins` in the server's working directory (`plugins/discovery.py:22-83`). |
| State | Global plugin manager. |
| Pure (remote-able) | Builtin plugin metadata, hints, prompts. |
| robotcode | No equivalent (this is server configuration). |

### manage_session — `server.py:3366-4301`
| Action | Host dependency | State |
|---|---|---|
| init | `session.import_library` → server-side instantiation; `_register_session_project_libraries` → libdoc (`server.py:618-638`); desktop guidance → `LibraryDocumentation("PlatynUI.BareMetal")`; tool-profile activation is global | W: imported/loaded libraries, search_order, variables, suite_level_variables |
| import_library | `import_library_for_session` (live namespace, `rf_native_context_manager.py:1435`) or bridge; `register_project_source` (libdoc of a server path) | W: libraries; project import spec |
| import_resource | `import_resource_for_session` (`1373`); variables_map sync; libdoc | W: variables, loaded_variable_files, context `resources` |
| set_variables | Runs Set Test/Suite/Global Variable through `execute_step`, or the bridge | W: suite_level_variables (+ a recorded step) |
| import_variables | Executes the Python variable file inside the server (`1474`) | W: variables, loaded_variable_files |
| start_test / end_test | Creates the context if needed, `start_test_in_context` / `end_test_in_context` (`699`, `749`); refused when attached | W: test_registry |
| add_data_row, list_tests, set_suite_setup, set_suite_teardown | None (pure) | W: TestInfo / suite metadata |
| set_tool_profile | Global tool visibility | Global |

- **robotcode replacements:**
  - Import actions: `Import Library` / `Import Resource` / `Import Variables` cells, or repl-server startup flags `-P`, `-V`, `-v`.
  - Test boundaries: just annotations in the state file.

### resume_batch
Covered under execute_batch. It reads and writes the batch state (TTL 300 s).

### run_test_suite — `server.py:7583-7702`
| Aspect | Detail |
|---|---|
| Purpose / params | Dry-run or execute a suite built from the session, or an existing file. Params: `session_id`, `suite_file_path`, `mode`, `validation_level`, `include_warnings`, `execution_options`, `output_level`, `capture_screenshots`. |
| Host deps | TestBuilder (see build_test_suite). Writes a temp suite. **Dry run:** subprocess `python -m robot --dryrun` (`components/execution/suite_execution_service.py:325-431`). **Full run:** in-process `run_cli` in a worker thread (`432-534`). Parses `output.xml` with `robot.api.ExecutionResult` (`701-845`). Refreshes the RF context afterwards (`execution_coordinator.py:651-670, 803-817`). `suite_file_path` is a server path. |
| State | Session resolution (can fall back to another session), artifacts. |
| Pure (remote-able) | Option → CLI mapping (`119-146`), dry-run stdout parsing (`590-700`). |
| robotcode | `robotcode robot [--dryrun] -v k:v -i tag suite.robot`, then `robotcode --format json results summary\|show\|log`. `robotcode --format json analyze code` is a static pre-check. |

### set_library_search_order — `server.py:6825-6893`
| Aspect | Detail |
|---|---|
| Purpose / params | Set library priority. Params: `libraries`, `session_id`. |
| Host deps | Only the project-name mapping from the libdoc store. The order takes effect at the next keyword (`keyword_executor.py:3934-3999`). |
| State | Writes `search_order` (`session_models.py:1402`). |
| Pure (remote-able) | Validation against imported libraries and project names. |
| robotcode | A `Set Library Search Order` cell. |

### visual_check — `server.py:7247-7325`
| Aspect | Detail |
|---|---|
| Purpose / params | Screenshot for visual validation. Params: `session_id`, `return_image`, `filename`. |
| Host deps | Runs Take Screenshot / Capture Page Screenshot in the RF context. Writes a PNG to `ROBOTMCP_SCREENSHOT_DIR` or the server temp dir and returns that server path. Can return an MCP image block (`ROBOTMCP_SCREENSHOT_MODE=image\|auto`). |
| State | Reads the session. |
| Pure (remote-able) | The visual hint text. |
| robotcode | `executeCell("Take Screenshot  filename=...")`. The file lands on the client, where the agent can read it directly. |

### build_test_suite — `server.py:5126-5235`; `components/test_builder.py:299-754`
| Aspect | Detail |
|---|---|
| Purpose / params | Render the recorded steps as a `.robot` suite. Params: `test_name`, `session_id`, `tags`, `documentation`, `remove_library_prefixes`, `bdd_style`, `data_driven_mode`, `include_pre_start`, `output_path`. |
| Host deps (7 places) | (1) Live namespace keyword→library map from `list_available_keywords` (`test_builder.py:2056-2071`). (2) Context `resources` list (`2115-2127`). (3) `detect_library_from_keyword` using `keyword_discovery` (`2405-2471`). (4) Libdoc project import specs and ambiguity check, only if the catalogue is already loaded (`2195-2239`, `4254-4308`). (5) Desktop replay preamble uses display classification from env and `/proc` (`3152-3239`). (6) `output_path` write to the server filesystem (`724-738`). (7) The `robot.api` model in `_create_rf_suite` (`2769`) needs the `robot` package, not a live context. |
| State | Reads the session: steps, test_registry, suite setup/teardown, flow_blocks, suite_level_variables + values, loaded_variable_files, imported_libraries, counters, desktop classification. |
| Pure (remote-able) | Everything else: session resolution; step reorder (`1817`); filters (`1972-2007`); optimize (`2241`); docs and setup/teardown (`2318-2403`); web-library conflict handling (`2564`); BDD transform (`782-1425`); embedded args (`1467-1625`); data-driven mode (`1626`); prefix strip (`4310`); OBS-11 propagation (`3323`); desktop introspection filter (`3258`); `.robot` text generation (`2828`); statistics and warnings (`4085`, `4034`). |
| robotcode | `robotcode --format json analyze code <file>` for validation; `robotcode robot` to run. Import detection could use the per-step `resolved_library` (already recorded, currently unused by the builder) or the repl `owner`. |

### fetch_artifact — `server.py:8586-8609`
| Aspect | Detail |
|---|---|
| Purpose / params | Read externalized content in pages. Params: `artifact_id`, `offset`, `limit`. |
| Host deps | Server artifact store on disk. Enabled only if the output mode is not inline **and** `ROBOTMCP_FETCH_ARTIFACT=true`. |
| State | Artifact store with TTL. |
| Remote note | Must be enabled, or set `ROBOTMCP_OUTPUT_MODE=inline`. Otherwise responses point to paths the client cannot read. |

---

## 3. Summary matrix

Column key:
- **Ctx** = live RF context/namespace
- **Inst** = live library instances
- **DOM** = DOM or screenshots
- **FS** = server filesystem
- **Pkg** = installed packages / libdoc
- **Proc** = spawns processes
- **Net** = outbound network
- **St** = server state (R/W)

| Tool | Ctx | Inst | DOM | FS | Pkg | Proc | Net | St | Remote-able core |
|---|---|---|---|---|---|---|---|---|---|
| analyze_scenario | – | Y | – | learn/mem | Y | – | attach, sampling | W | NLP, profiles |
| recommend_libraries | Y (with session) | Y | – | – | Y | – | sampling | RW | ranking |
| check_library_availability | – | status | – | Y | Y | (pip helper) | – | – | none |
| execute_step | Y | Y | Y | Y | Y | desktop | attach | RW | pre/post pipeline |
| execute_batch / resume_batch | Y | Y | Y | Y | Y | – | – | RW (+ TTL) | resolver, policy |
| execute_flow | Y | Y | – | – | – | – | – | W | block record |
| find_keywords | session strategy | Y | – | project files | Y | – | – | R | ranking, filters |
| get_keyword_info | session mode | – | – | project files | Y | – | attach | R | scoping, hints |
| get_locator_guidance | – | – | – | – | – | – | – | – | all |
| get_session_state | Y | Y | Y | artifacts | Y | /proc | attach | RW | filtering, delta |
| intent_action | Y | Y | – | – | – | – | – | R (all sessions) | resolution |
| manage_attach | – | – | – | – | – | – | Y | W | – |
| manage_library_plugins | – | – | – | manifests | entry points | – | – | global | metadata |
| manage_session | Y | Y | – | Y | Y | – | attach | RW | registry ops |
| run_test_suite | Y (refresh) | – | – | Y | Y | Y | – | R | option mapping, parsing |
| set_library_search_order | (next step) | – | – | – | project names | – | – | W | all |
| visual_check | Y | Y | Y | Y | – | – | – | R | – |
| build_test_suite | R | – | – | output_path | Y | – | – | R | ~90% |
| fetch_artifact | – | – | – | Y | – | – | – | R | – |

---

## 4. Hidden / legacy tools

These are registered with `DISABLED_TOOL_KWARGS`. The disabled set is at `server.py:~8800-8848`.

| Tool (server.py line) | Host dependency | Notes |
|---|---|---|
| list_library_plugins 1509, reload_library_plugins 1540, diagnose_library_plugin 1558 | Entry points / manifests | Metadata is pure |
| discover_keywords 3348 | Libdoc registry | Legacy semantic search |
| get_application_state 5084 | Live (state_manager) | |
| suggest_next_step 5104, validate_scenario 5295 | None | Pure NLP |
| load_test_data 5238 | Server FS (CSV/Excel/JSON, optionally DataDriver) | Client file read would replace it |
| get_page_source 5436 | Live DOM | |
| get_library_status 5512, get_available_keywords 5525, search_keywords 5544, get_loaded_libraries 7481 | Installed packages / instances | |
| evaluate_expression 5924, set_variables 5946, execute_if 6216, execute_for_each 6233, execute_try_except 6252 | Live context | |
| get_keyword_documentation 6501, get_library_documentation 6586, debug_parse_keyword_arguments 6669 | Libdoc | |
| validate_test_readiness 6809, get_session_validation_status 7705, get_session_info 7148 | None | Server state |
| initialize_context 6896 | Instances | |
| get_context_variables 7078, diagnose_rf_context 7750 | Live context | |
| get_selenium_locator_guidance 7328, get_browser_locator_guidance 7365, get_appium_locator_guidance 7409 | None | Pure |
| run_test_suite_dry 7487 | Subprocess | |
| attach_status 8400, attach_stop_bridge 8438 | Network | |
| import_resource 8462, import_custom_library 8480, list_available_keywords 8505, get_session_keyword_documentation 8559 | Live namespace / bridge | |
| Memory tools (recall_step, recall_fix, recall_locator, store_knowledge, get_memory_status), `domains/memory/adapters/fastmcp_adapter.py:96-218`, registered at `server.py:8850-8868` | sqlite-vec + embedding model on the server | Only when `ROBOTMCP_MEMORY_ENABLED` |
| Prompts `automate` 1459, `learn` 1480 | None | Pure |

---

## 5. Intelligence pipelines and their inputs

| Pipeline | Location | Exact inputs | Needs live objects? | Remote-able / robotcode route |
|---|---|---|---|---|
| **Error hints** | `utils/hints.py:813` `generate_hints`; `HintContext` at `29` | `{session_id, keyword, arguments, error_text, use_context, session_search_order}`. Imports only `re`, `urllib`, `requests_guidance`. Also plugin failure hints (`plugins/manager.py:210`; Requests `plugins/builtin/requests_plugin.py:87`, PlatynUI `plugins/builtin/platynui_plugin.py:952` — text only), link/image guidance (`keyword_executor.py:1137`), rank/dedupe (`1112`), deprecation alias (`domains/shared/kernel.py`) | No | **Fully pure.** Feed it the `executeCell` status/message. |
| **Pre-validation** | Decision: `keyword_executor.py:971` (curated set + `LocatorArgIntrospector` veto using libdoc arg names; desktop skip), `1073` (locator extraction), `2386-2400` (timeout precedence). Probe: `1226-1330` (owner via `EXECUTION_CONTEXTS…get_runner`), `1332` (retry 200 ms), Browser `1452-1600` (`Get Element States` + temporary `Set Browser Timeout` under a lock), Selenium `1604-1728` (Get WebElements + JS), Appium `1729-1868`. Failure hints `2412-2548` | Keyword, arguments, owner library, timeout; then live element states | Probe: yes | The decision and hint composition are pure. The server could emit a pre-flight RF line (e.g. `Get Element States  loc  validate  ...` or `Wait Until Element Is Visible  loc  0.5s`) for the agent to run first. |
| **Timeout injection** | `domains/timeout/keyword_classifier.py:212`; policy via `container.py:181` (defaults: action 5 s, navigation 60 s, assertion 10 s, read 2 s); inject at `keyword_executor.py:3387`; desktop query settings at `3310` | Keyword, arguments, timeout_ms, owner library (static fallback maps exist when there is no context) | Only the desktop part (writes `${PLATYNUI_QUERY_SETTINGS}` into live Variables) | Pure given the owner library (from libdoc or repl `owner`). |
| **PostActionVerifier** (feature branch only) | `post_action_verifier.py` (feature branch) | Keyword, arguments, result, `session.browser_state`. Browser-only; runs `Browser.Evaluate Javascript` via `BuiltIn.run_keyword` within 50 ms (hidden parent, fill value, checked state, select value) | Yes | The server could generate post-check lines (e.g. `Get Property loc value == x`). |
| **WrapperSuggester** (feature branch only) | `wrapper_suggester.py:223-350` (feature branch) | Session (active library), failed locator, keyword. JS ancestor walk (≤10 hops, 100 ms) via Browser Evaluate JavaScript; `_build_hint_from_raw` is pure | Yes (the probe) | The agent runs the JS probe cell; the server turns its JSON into hints. |
| **actionable_elements** (feature branch) / **actionable_controls** (this branch) | Feature branch: `ActionableElementsCollector` in `page_source_service.py`. This branch: `ui_tree_service.py:808` | Web: Browser JS (live) **or** HTML → BeautifulSoup (`_collect_from_html`, pure). Desktop: native PlatynUI runtime | Web JS and desktop: yes | HTML path is pure given page source from `executeCell`. Desktop: no equivalent. |
| **Locator conversion** | `components/execution/locator_converter.py:233-460`; **off by default** (`models/config_models.py:55`); caller `execution_coordinator.py:443`. Intent normalizer in `domains/intent/adapters/locator_normalizer_adapter.py`. Browser pre-validation `id=` rewrite at `keyword_executor.py:1392` | Locator string + `browser_state.active_library` (set only after live owner detection, `keyword_executor.py:4064-4108`) | No | Pure. |
| **Keyword resolution / search order** | BDD strip (`domains/keyword_resolution/services.py:18`); plugin keyword→library map (`plugins/manager.py:173`); `session.search_order` built by profiles (`session_models.py:1207`), `import_library` (`357-363`), `recommend_libraries`, `set_library_search_order` (`1402`); applied at execution (`keyword_executor.py:3934-3999`, `rf_native_context_manager.py:560-576`); owner and `qualified_keyword` captured after execution (`keyword_executor.py:4026-4062`) | Session lists + live namespace | Resolution itself: yes | Search order is pure state. Resolution comes from the repl `owner`. Ambiguity via libdoc of each import or `analyze code`. |
| **Test building (BDD / embedded / data-driven)** | `components/test_builder.py` (section 2) | Recorded steps, TestRegistry, suite metadata, suite variables; plus the host items listed under build_test_suite | Only the listed host items | ~90% pure. Replace the namespace map with recorded `resolved_library`. |
| **Response shaping / tokens** | detail_level (`keyword_executor.py:4718-4919`); enhanced serializer patch (`utils/enhanced_serialization_integration.py`); ADR-015 externalization (`server.py:186-217`, `domains/artifact_output/services.py:126`); ADR-018 delta (`domains/snapshot/delta_service.py`); token estimation (`domains/token_accounting/services.py`, tiktoken optional). `ResponseCompressor` (`domains/response_optimization`) is **not wired in** — `_response_optimization_configs` at `server.py:80` is unused | Result dict, `session.variables` (raw), `browser_state` | No (but externalization writes to the server filesystem) | Pure. Use inline mode or enable `fetch_artifact` remotely. |
| **Semantic memory (ADR-014)** | `domains/memory/services.py:356-833`; hooks `on_tool_call` (`750`) and `augment_response` (`665`, 50 ms budget, `server.py:160-183`) | Tool name, arguments, result text | No; needs an embedding model plus the DB | Remote-able server-side (per `ROBOTMCP_PROJECT_ID`). A client-file variant would need client-side embeddings. |
| **Library recommender** | `library_recommender.py:122` | Scenario, context, explicit preference | Only for availability / auto-import | Pure core. |
| **Intent resolution** | `domains/intent/*` | Intent, target, value, options, match, nth, mode, `imported_libraries`, session map | No (execution: yes) | Pure; the agent executes. |
| **Plugin system** | `plugins/manager.py`, `plugins/builtin/*` | Static metadata, keyword maps, incompatibility tables, alternatives (pure). Live pieces: Drag-and-Drop pre-scroll (`browser_plugin.py:444-501`), Requests `before_keyword_execution` / `on_session_start` (`requests_plugin.py:58-86`, `session_manager.py:106-168`), state providers (`browser_plugin.py:21-117`, `selenium_plugin.py:19-78`), PlatynUI runtime helpers. Discovery: entry points + manifests (server) | Partly | Keep the pure tables. Live hooks become snippets. |
| **Attach bridge** | Server side `attach/mcp_attach.py:135-782`: RF library in the *user's* RF process, an HTTP thread plus a command queue drained by the `MCP Serve` loop. Verbs (`337-398`): diagnostics, run_keyword, import_library/resource/variables, list_keywords, get_keyword_doc, get/set_variable(s), get_page_source, get_aria_snapshot, get_session_info, stop, force_stop. Client `external_rf_client.py:25-190` (POST + `X-MCP-Token`) | Wired into execute_step, manage_session imports and set_variables, get_session_state, analyze_scenario, keyword docs | Execution happens client-side, **but the server connects inbound to the user's machine**. It skips pre-validation, hints and recording | Closest existing analogue to the target design. Replaced by `robotcode repl-server` (`executeCell`) or `robotcode debug` / `robot-debug` (DAP evaluate at breakpoints), driven by the agent. |
| **Instruction learning** | `optimization/instruction_hooks.py:240`, `server.py:122-157` | Tool name, arguments, success, error, result | No; persists to `~/.rf-mcp` | Pure. Disable or keep per tenant. |
| **LLM sampling** | `utils/sampling.py` | Scenario text | No; uses MCP client sampling | Pure. |

---

## 6. Minimal session state model for execute_step → build_test_suite

### 6.1 What the builder actually reads
**From `ExecutionSession`** (`models/session_models.py:117-205`, `models/execution_models.py:10-170`):
- `session_id`, `last_activity` (session resolution).
- `steps: [ExecutionStep]` in legacy mode. Via `_get_session_steps` (`test_builder.py:1786-1808`) it uses: `keyword` (may be qualified `Lib.Kw`), `arguments` (original strings), `status`, `step_id`, `assigned_variables` (`${x}` form), `assignment_type`, `error`, `result`, start/end time (duration).
- `test_registry`:
  - `tests` (ordered): name → `TestInfo {name, status, documentation, tags, template, data_rows, named_data_rows[(name, values)], setup, teardown, steps, flow_blocks, started_at, ended_at, error_message}`
  - `current_test_name`
  - private `_multi_test_activated` — must be persisted.
- `suite_setup`, `suite_teardown` (`{keyword, arguments}`).
- `suite_level_steps` (counted for warnings only).
- `flow_blocks` (session-level).
- `suite_level_variables` (names) + `variables[name]` values — **only these values are needed**.
- `loaded_variable_files` (paths).
- `imported_libraries`, `explicit_library_preference` (web-library conflict handling).
- Desktop classification: `platform_type`, `session_type`, `imported_libraries`.
- `executed_step_count`, `failed_step_count`.
- Per step in multi-test mode: `bdd_group`, `bdd_intent`, `str(result)` as `captured_value` (`test_builder.py:1706-1735, 3055-3076`).

**From stores outside `ExecutionSession`** (must be added to a portable state):
- Context `resources` list (`rf_native_context_manager.py:1400-1403`).
- Per-session project import specs `{ns_name: {spec path, args, alias, type, keyword names}}` (`rf_libdoc_integration.py:696-702`).
- Keyword→library map. It comes from the live namespace today; it can be derived from each step's `resolved_library`.

### 6.2 What execute_step needs carried between calls (server-side intelligence)
- `imported_libraries`, `search_order`, `explicit_library_preference`, `preference_source`, `session_type`, `platform_type`, `loaded_libraries`
- `browser_state.active_library` (+ `current_url`)
- The current test (record-gate carve-out and step routing)
- Timeout-policy overrides (defaults are constants)
- Serializable variable names and values
- Batch resume state; delta-state version; `scenario_text`; `auto_configured`

### 6.3 Serializable sketch (fits in a client file, e.g. `.rfmcp/<session_id>.json`)
```json
{"session_id":"...", "scenario_text":"...", "session_type":"web_automation", "platform_type":"web",
 "explicit_library_preference":"Browser", "preference_source":"rule",
 "imported_libraries":["BuiltIn","Browser"], "search_order":["Browser","BuiltIn"],
 "active_library":"browser", "project_imports":{"acme":{"spec":"./libs/acme.py","args":[],"alias":null,"type":"LIBRARY","keywords":["Acme Add"]}},
 "resources":["./res/common.resource"], "variable_files":[{"path":"vars.py","args":[]}],
 "suite_variables":{"BASE_URL":"https://..."},
 "suite_setup":null, "suite_teardown":null, "flow_blocks":[],
 "steps":[{"keyword":"Fill Text","arguments":["id=u","${USER}"],"status":"pass","assigned":["${x}"],
           "assignment_type":"single","captured_value":"42","resolved_library":"Browser","bdd_group":null,"bdd_intent":null}],
 "multi_test":{"activated":false,"current":null,"tests":[]},
 "counters":{"executed":7,"failed":1}, "batch":null}
```

### 6.4 Fields that must be dropped or coerced
- `ExecutionStep.result` and `session.variables` hold **raw Python objects** (Response, WebElement, Popen). Keep only a string `captured_value` and the string suite variables.
- Drop: `browser_state.driver_instance`, `_temp_objects` (`keyword_executor.py:4406-4440`), the `_session_manager` back-reference, `desktop_aut_pid` / `desktop_aut_sid`, `_platynui_*`, the desktop one-shot flags, all RF context objects in `_session_contexts`, and the raw `BatchState.results_map` values (stringify them).
- Sets become lists, datetimes become ISO strings, `named_data_rows` tuples become lists. OrderedDict order must be preserved.

### 6.5 Gaps found while mapping
1. **Legacy mode drops BDD annotations.** `_get_session_steps` does not copy `bdd_group` / `bdd_intent` into the step dicts, while `_build_test_case` reads `step.get("bdd_group")` (`test_builder.py:1786-1808` vs `2010`). Explicit BDD grouping therefore appears to work only in multi-test mode.
2. **The builder ignores `step.resolved_library`** for imports and relies on the live namespace instead.
3. **Import-relevant state (resources, project specs) lives outside `ExecutionSession`.**
4. **Attach-bridge steps are never recorded** (section 1, row 7).

---

## 7. What this means for the remote design
- **Pure and liftable as-is:** get_locator_guidance; all hint and plugin-text logic; intent resolution; library recommendation ranking; NLP and session profiling; search-order bookkeeping; the ${STEP_N} resolver; recovery strategy selection; the test builder (after the four host hooks are replaced); response shaping; delta diffing; memory and learning (as server-side stores).
- **Host-bound and needing client primitives:** every keyword execution, pre-validation, page source / aria / variables / ui_tree, screenshots, availability checks, all discovery (libdoc of the *user's* environment), suite runs, and every desktop/PlatynUI safety and focus signal (os, `/proc`, native runtime — no robotcode equivalent).
- **Must be redesigned for a stateless or multi-tenant server:**
  - Session-resolution fallbacks and all-session intent inference (cross-user leakage).
  - Global tool profiles.
  - Artifact paths on the server filesystem.
  - `output_path` and `visual_check` returning server paths.
  - Batch/delta caches kept in memory.
  - Learning and memory writing to the server's `~/.rf-mcp`.
- **robotcode coverage:**
  - Execution: `repl-server` `executeCell`, which needs a persistent process plus a JSON-RPC client.
  - Discovery/docs: `libdoc` (spec JSON).
  - Availability: `libdoc version` or `discover info`.
  - Static validation: `analyze code`, which is new capability rf-mcp lacks.
  - Runs: `robot` / `robot --dryrun` plus `results summary|show|log`.
  - Debug-time attach: `debug` / `robot-debug` (DAP).
  - No equivalent: live namespace listing, bounded desktop tree dump, focus/steering signals.

## 8. Key files (absolute paths)
- ~/workspace/rf-mcp-robotcode/src/robotmcp/server.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/keyword_executor.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/rf_native_context_manager.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/execution_coordinator.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/suite_execution_service.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/page_source_service.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/ui_tree_service.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/locator_converter.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/external_rf_client.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/execution/session_manager.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/test_builder.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/keyword_matcher.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/library_recommender.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/nlp_processor.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/components/state_manager.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/models/session_models.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/models/execution_models.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/core/library_manager.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/utils/hints.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/utils/rf_libdoc_integration.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/utils/library_checker.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/utils/session_resolution.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/plugins/manager.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/plugins/discovery.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/plugins/builtin/ (browser_plugin.py, selenium_plugin.py, requests_plugin.py, platynui_plugin.py)
- ~/workspace/rf-mcp-robotcode/src/robotmcp/domains/intent/ (services.py, weak_model_guards.py, adapters/)
- ~/workspace/rf-mcp-robotcode/src/robotmcp/domains/memory/services.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/domains/batch_execution/ (services.py, aggregates.py)
- ~/workspace/rf-mcp-robotcode/src/robotmcp/domains/artifact_output/value_objects.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/adapters/recovery_adapter.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/adapters/page_state_adapter.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/attach/mcp_attach.py
- ~/workspace/rf-mcp-robotcode/src/robotmcp/container.py
- ~/workspace/rf-mcp-robotcode/.venv/lib/python*/site-packages/robotcode/repl_server/protocol.py
- ~/workspace/rf-mcp-robotcode/.venv/lib/python*/site-packages/robotcode/repl_server/interpreter.py