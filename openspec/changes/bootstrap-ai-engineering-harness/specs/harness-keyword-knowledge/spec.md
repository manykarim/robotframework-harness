## Purpose

Gives the agent accurate keyword documentation and search for exactly the libraries and resources its tests import, produced locally and offline, without uploading specs anywhere.

## ADDED Requirements

### Requirement: Imports produce keyword index and documentation files

When a test file, resource file or REPL session that the agent edits or runs imports a
library or resource, the harness SHALL write two local files for it: a one-line-per-keyword
index (name and arguments) and a full documentation file. Libraries and resources imported
by path from the project SHALL be included. The files MUST be produced without network
access, and the harness MUST NOT send library specifications to any remote service.

#### Scenario: Browser import yields greppable docs

- **WHEN** the agent adds `Library    Browser` to a test file
- **THEN** an index file lists every Browser keyword with its arguments, one per line, and a full documentation file exists for Browser

#### Scenario: project resource by path

- **WHEN** a suite imports `Resource    ${CURDIR}/common.resource`
- **THEN** the resource's keywords appear in its own index and documentation files

### Requirement: Failures point to the failing keyword's documentation

When a live step fails, the feedback SHALL give the path of the failing keyword's
documentation file. Reading that path SHALL yield the keyword's full documentation, even if
the file was not generated before.

#### Scenario: on-demand keyword doc

- **WHEN** a `Select Options By` step fails and the agent reads the documentation path given in the feedback
- **THEN** the file contains the keyword's full documentation including arguments and examples

### Requirement: Keyword search by intent works offline

The harness SHALL provide local keyword search by natural-language intent across the
imported libraries and project resources. On the project's keyword-search benchmark it MUST
return the expected keyword within the top five results for at least 90% of queries, and it
MUST answer in under 100 ms after indexing.

#### Scenario: intent query

- **WHEN** the agent searches for "choose an option in a dropdown" with Browser imported
- **THEN** `Select Options By` is among the top five results
