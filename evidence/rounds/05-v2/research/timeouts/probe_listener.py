import sys, os
ROBOT_LISTENER_API_VERSION = 3
def _p(*a): sys.__stdout__.write("[probe] " + " ".join(str(x) for x in a) + "\n"); sys.__stdout__.flush()
_p("loaded argv=", sys.argv[:4], "pid", os.getpid())
def start_suite(data, result): _p("start_suite", data.name, repr(data.source))
def start_test(data, result): _p("start_test", data.name)
def library_import(library, importer): _p("library_import", library.name, type(library).__name__, "instance?", hasattr(library, "instance"), "importer", importer)
def end_keyword(data, result): _p("end_keyword", result.name, getattr(result, "owner", None), result.status, result.elapsed_time)
