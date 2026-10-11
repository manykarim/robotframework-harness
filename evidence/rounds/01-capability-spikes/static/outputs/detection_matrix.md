| case | planted class | expect | analyze (real libs) | analyze codes | robot --dryrun (rf-mcp today) | analyze w/ spec stubs (server-side) | dryrun w/ typed stubs (server-side) |
|---|---|---|---|---|---|---|---|
| b01_typo_keyword | keyword-typo | error | caught | KeywordNotFound | caught | caught | caught |
| b02_too_few_args | arg-count | error | caught | DataError | caught | caught | caught |
| b03_too_many_args | arg-count | error | caught | DataError | caught | caught | caught |
| b04_unknown_named_arg | named-arg | error | caught | DataError | caught | caught | caught |
| b05_undefined_variable | variable | error | caught | VariableNotFound | clean | caught | clean |
| b06_missing_library_import | import | error | caught | KeywordNotFound | caught | caught | caught |
| b07_browser_kw_with_selenium_only | wrong-library | error | caught | KeywordNotFound | caught | caught | caught |
| b08_ambiguous_two_custom_libs | ambiguous | error | caught | MultipleKeywords | caught | caught | caught |
| b09_ambiguous_browser_selenium | ambiguous | error | caught | MultipleKeywords | caught | caught | caught |
| b10_bad_embedded_call | embedded | error | caught | KeywordNotFound | caught | caught | caught |
| b11_invalid_for | syntax-for | error | caught | ModelError | caught | caught | caught |
| b12_for_missing_end | syntax-for | error | caught | ModelError | caught | caught | caught |
| b13_invalid_if | syntax-if | error | caught | ModelError | caught | caught | caught |
| b14_wrong_setting_name | setting | error | caught | TokenError | caught | caught | caught |
| b15_resource_path_wrong | import | error | caught | DataError | caught | caught | caught |
| b16_browser_missing_arg | arg-count | error | caught | DataError | caught | caught | caught |
| b17_browser_positional_after_named | named-arg | error | caught | DataError | caught | caught | caught |
| b18_requests_missing_url | arg-count | error | caught | DataError | caught | caught | caught |
| b19_requests_on_session_missing_url | arg-count(kwargs-sig) | error | clean | - | clean | clean | clean |
| b20_single_space_separator | keyword-typo | error | caught | KeywordNotFound | caught | caught | caught |
| b21_library_not_installed | import | error | caught | DataError | caught | caught | caught |
| b22_library_init_args | import-args | error | clean | - | caught | caught | caught |
| b23_wrong_library_prefix | keyword-typo | error | caught | KeywordNotFound | caught | caught | caught |
| b24_unclosed_variable | variable-syntax | error | caught | TokenError | clean | caught | clean |
| b25_return_in_test | syntax | error | caught | TokenError | caught | caught | caught |
| b26_unknown_section | syntax | error | caught | InvalidHeader | caught | caught | caught |
| b27_assertion_operator_typo | type-conversion | error | clean | - | caught | clean | caught |
| b28_int_conversion | type-conversion | error | clean | - | caught | clean | caught |
| b29_user_kw_too_many_args | arg-count | error | caught | DataError | caught | caught | caught |
| b30_selenium_kw_in_browser_session | wrong-library | error | caught | KeywordNotFound | caught | caught | caught |
| b31_empty_test | syntax | error | caught | ModelError | caught | caught | caught |
| b32_duplicate_test | duplicate | warn | clean | - | caught | clean | caught |
| b33_keyword_only_missing | named-arg | error | caught | DataError | caught | caught | caught |
| v01_builtin_ok | control | ok | OK | - | OK | OK | OK |
| v02_bdd_user_keyword | control-bdd | ok | OK | - | OK | OK | OK |
| v03_bdd_on_library_kw | control-bdd | ok | OK | - | OK | OK | OK |
| v04_assign_then_use | control-variable | ok | OK | - | OK | OK | OK |
| v05_dynamic_set_test_variable | control-variable(dynamic) | ok | **FP** | VariableNotFound | OK | **FP** | OK |
| v06_cli_variable | control-variable(cli -v) | ok | **FP** | VariableNotFound | OK | **FP** | OK |
| v06_cli_variable+cli-var | control-variable(cli -v) | ok | OK | - | OK | n/a | n/a |
| v07_search_order_resolves_ambiguity | control-ambiguous | ok | **FP** | MultipleKeywords | OK | **FP** | OK |
| v08_qualified_name | control-ambiguous | ok | OK | - | OK | OK | OK |
| v09_browser_ok | control-browser | ok | OK | - | OK | OK | OK |
| v10_requests_ok | control-requests | ok | OK | - | OK | OK | OK |
| v11_selenium_ok | control-selenium | ok | OK | - | OK | OK | OK |
| v12_robot_toml_variable | control-variable(robot.toml) | ok | OK | - | OK | OK | OK |
| v13_suite_variable_env_var | control-variable(env) | ok | OK | - | OK | OK | OK |
| v14_var_syntax_rf7 | control-syntax | ok | OK | - | OK | OK | OK |
| v15_timeout_named_kw_only | control-named | ok | OK | - | OK | OK | OK |

Broken cases caught (of 33): analyze 28, dryrun 30, analyze+dryrun union 32, stub-analyze 29, typed-stub dryrun 30.
False positives on 16 valid controls: analyze ['v05_dynamic_set_test_variable', 'v06_cli_variable', 'v07_search_order_resolves_ambiguity'], dryrun [].
