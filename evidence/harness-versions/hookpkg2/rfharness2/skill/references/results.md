# Running robot and reading output.xml

RESULTS / output.xml ANALYSIS

Run:
  robot -d results tests/                      # or: robotcode robot -d results tests/
  robot -d results -t "Login*" -i smoke tests/ # select by test name / tag;  --dryrun = syntax/keyword check only
  Exit code = number of failed tests (0 = all passed). Files: results/output.xml, log.html, report.html.

Inspect a finished run WITHOUT re-running (robotcode results; -o selects the file, default from robot.toml):
  robotcode results summary -o results/output.xml            # counts + overall status
  robotcode results show --failed -o results/output.xml      # one line per failed test: name, path:line, message
  robotcode results log "*Login*" -o results/output.xml      # keyword tree of matching tests (args, messages)
  robotcode results stats --by tag -o results/output.xml     # aggregate by tag/suite/status
  robotcode results diff old/output.xml new/output.xml       # status changes between runs
  robotcode --format json results summary -o results/output.xml   # machine-readable
  NOTE: `-o` belongs AFTER the subcommand (robotcode results show -o FILE).

Custom analysis with Robot Framework's API (no extra packages):
  python - <<'PY'
  from robot.api import ExecutionResult, ResultVisitor
  res = ExecutionResult("results/output.xml")
  s = res.statistics.total
  print("passed", s.passed, "failed", s.failed, "skipped", s.skipped)
  class Failed(ResultVisitor):
      def visit_test(self, test):
          if test.status == "FAIL":
              print(test.full_name, "|", test.message.splitlines()[0] if test.message else "", "|", test.elapsed_time)
  res.visit(Failed())
  for t in res.suite.all_tests:               # every test: name, status, tags, elapsed
      print(t.name, t.status, list(t.tags), t.elapsed_time.total_seconds())
  PY
  Keyword level: walk test.body (kw.name, kw.status, kw.args, kw.message, kw.elapsed_time; nested kw.body).
  Merge/re-report: rebot --merge -d merged a/output.xml b/output.xml ; rebot --output NONE --log log2.html output.xml
