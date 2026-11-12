# Maven and Gradle dependency resolution (milestone 2)

See the [complete parameter reference](SECURITY_CLI_REFERENCE.md) for all build
options, defaults, restrictions and example commands.

This milestone was added after the original four-stage roadmap. It resolves JVM
dependencies for a trusted local project and assesses the selected versions.
Existing JavaScript and Python lockfile scanning remains part of milestone 1.

## Try it locally

Install OSV-Scanner v2 and use a local checkout of the project. A Java runtime
compatible with the project's Maven/Gradle version is required. The command
prefers an executable project wrapper (`mvnw`/`gradlew`); otherwise it uses the
installed `mvn`/`gradle`. Select another trusted executable with `--maven PATH`
or `--gradle PATH`.

```bash
# Spring Boot / Maven: resolve inherited and transitive dependency versions.
agent-do security scan --path /path/to/project --resolve maven --json

# Select production profiles and repository settings.
agent-do security scan --path /path/to/project --resolve maven \
  --maven-profile prod --maven-profile cloud \
  --maven-settings /path/to/settings.xml --json

# Override a build property used by dependency management.
agent-do security scan --path /path/to/project --resolve maven \
  --build-property spring-framework.version=6.1.14 --json

# Gradle: scan the runtime classpath of each applicable project.
agent-do security scan --path /path/to/project --resolve gradle --json

# Include test dependencies or use a project-specific configuration.
agent-do security scan --path /path/to/project --resolve gradle \
  --gradle-configuration runtimeClasspath \
  --gradle-configuration testRuntimeClasspath --json

# Apply the usual presentation filters without dropping saved evidence.
agent-do security scan --path /path/to/project --resolve maven \
  --cvss-min 7 --include-unscored --scan-timeout 600 --json
```

The command prints one JSON document. Reports and the generated resolved SBOM
are saved inside the report under `$AGENT_DO_HOME/security/reports/` (by default,
`~/.agent-do/security/reports/`). A later `security report --latest` can filter it
without running the build again.

Exit 0 means the selected dependency assessment completed, including assessments
that found vulnerabilities. Exit 1 means incomplete coverage. Exit 2 indicates
invalid command options. A successful build resolution with an unavailable
scanner still saves resolved inventory, but exits incomplete.

## Explicit build execution

`--resolve` is the opt-in: it executes local project code, extensions, wrappers,
and applicable user build configuration. Maven/Gradle may access configured
repositories, download metadata/plugins/dependencies, and write caches or
project files. This is not an execution sandbox. No compile, test, install,
publish, or deployment task is requested by the resolver, but project build
code can have its own side effects.

Ordinary file scans never invoke the build tools. Build-related options without
`--resolve` are rejected. Resolution is currently local only: clone a GitHub
project, inspect/trust it, then use `--path`. `--repo ... --resolve ...` is
rejected so a repository link cannot silently become remote code execution.

Timeouts kill the resolver process group. Captured build output and the
generated inventory are bounded by `--max-bytes`. The default `--scan-timeout`
is 300 seconds **per invocation**, including the version probe. Full build logs
are not saved or echoed because they can contain credentials. For a failed
resolution, run the documented build goal directly to diagnose it.

`--build-property NAME=VALUE` becomes a Maven `-D` property or Gradle `-P` project
property. Report metadata records property names, not values. Avoid credentials
in CLI properties; use settings or existing credential mechanisms instead.
Inventory-control properties are reserved and cannot be overridden by this flag.

## Maven behavior

### Private Maven repositories (Artifactory/Nexus)

Maven retains its normal settings behavior, including `~/.m2/settings.xml` and
environment-based configuration. The plugin does not replace your home directory
or require repository credentials as plugin arguments. To select a settings file:

```bash
agent-do security scan --path ~/workspace/offer-service --resolve maven \
  --maven-settings ~/.m2/settings.xml --severity critical --include-unscored --json
```

`--maven-settings PATH` (alias `--settings PATH`) is forwarded as Maven's
`--settings PATH`. For example, the shorter form is:

```bash
agent-do security scan --path ~/workspace/offer-service --resolve maven \
  --settings ~/.m2/settings.xml --severity critical --json
```

Ensure the settings `<server><id>` matches the
repository or mirror ID used by the project, the necessary profiles are active,
and any credential environment variables referenced by settings are available
to the process. Keep credentials in your existing settings/credential mechanism,
not in build properties or repository-list URLs. Settings contents are not copied
into the report; the settings path is recorded.

If resolution fails, the error points to settings and repository access. Diagnose
with the project's normal Maven command in your terminal using the same settings
and profiles; build logs are deliberately not persisted in security reports.
The scanner can assess private Maven projects when their normal dependency
resolution succeeds; it does not supply missing repository authorization.

If you still see a build failure without any settings guidance after updating,
check which checkout your installed `agent-do` points to. From the updated
checkout, invoke `./agent-do security ...` directly to avoid an older installation.

### Resolved inventory

The resolver invokes the pinned goal
`org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree`, with JSON output
and verbose conflict output disabled. It captures JSON trees from stdout,
including reactor modules, rather than writing dependency-tree files into each
module. Maven's effective resolution applies parent POMs, imported BOMs,
dependency management, active profiles, exclusions, and conflict mediation.
Omitted versions are not treated as installed dependencies.

For example, a POM can omit `spring-web`'s version because Spring Boot manages
it. The returned tree supplies the selected version; the report records that
version and the path from the application to `spring-web` and its dependencies.
Compile, runtime, provided, system, and test scopes are preserved as Maven
reports them. The command does not claim that every scope is shipped to production.

The selected root's reactor is assessed using normal Maven behavior. Requested
profiles and settings location are recorded. Profiles activated implicitly by
settings, environment, JDK, files, or defaults also affect Maven's returned tree;
the metadata is not an independently enumerated list of effective active profiles.
Run with the same environment/settings as the build whose dependencies matter.

Each module is mapped back to its source POM using artifact/group identity.
Ambiguous mappings and unmapped/outside-root modules remain coverage gaps.
Independent POMs in the repository that are not in the selected reactor remain
file-only assessments with unresolved transitive coverage. Scan their roots
separately. A failed reactor or missing tree never becomes a clean result.
Projects that require artifacts installed by another build may need their normal
build preparation first; this command does not silently run `install`.

For a direct diagnostic run:

```bash
./mvnw --batch-mode --no-transfer-progress -Dstyle.color=never \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree \
  -DoutputType=json -Dverbose=false
```

## Gradle behavior

The resolver injects its bundled Groovy init script and requests only the
`:agentDoSecurityInventory` task. It disables the persistent daemon and
configuration cache for this invocation. The script uses Gradle's
`ResolutionResult` API, not parsing the human-readable `dependencies` task.
It works with Groovy and Kotlin build scripts through that API. The implementation
targets modern Gradle 7+ APIs; use a Java runtime supported by your wrapper.

By default it resolves `runtimeClasspath` across the root build's projects.
Repeat `--gradle-configuration` to choose runtime, compile, test, annotation
processor, Android variant, or custom configurations explicitly. Those choices
define the report scope; unselected configurations are not claimed assessed.

Graph nodes identify the selected versions after constraints, BOM/platform
alignment, dependency substitution, and conflict resolution. Evidence retains
the requesting selector and selection reasons. Project dependencies are
traversed without pretending that local project coordinates are published
external packages. The report retains graph edges and a canonical dependency
path for each reachable external component; it does not enumerate exponentially
many alternative paths through shared graph nodes.

Missing/unresolvable requested configurations, unresolved edges, local file/JAR
dependencies, and composite included builds are explicit gaps. Aggregator
projects without resolvable configurations do not by themselves cause failure.
Scan included builds separately. Buildscript/plugin dependency classpaths are
outside this application-configuration inventory.

## Evidence and scanner matching

Reports contain a `resolution` section with tool/executable/version, selected
profiles/configurations, source module mappings, raw dependency trees/graphs,
exact package coordinates, scopes, dependency paths, and an inventory hash.
The graph describes this resolution run; it does not establish which artifacts
were previously installed, packaged into a Spring Boot JAR, or deployed.

The resolver creates a CycloneDX 1.5 SBOM with Maven package URLs from the
selected coordinates. That SBOM is fed to OSV-Scanner alongside the remaining
file inventories. Successfully resolved JVM manifests and adjacent Gradle locks
are replaced in the temporary scanner snapshot, so stale lockfile versions or
unexpanded POM declarations cannot create conflicting matches for the same scope.
Original input files remain in the report's initial inventory and are not
deleted from the project by the scanner.

Every resolved component must appear in the scanner's returned package inventory.
Missing components or missing SBOM results make coverage incomplete. Findings
from the SBOM receive the original module, source manifest, scope/configuration,
and dependency path. Available findings survive partial-resolution gaps.
An empty successfully resolved application graph is valid and requires no
vulnerability lookup for nonexistent dependencies.

## Verification and current limits

```bash
python3 tests/test_security.py
python3 tests/test_security_resolution.py
./agent-do harness contracts validate
./agent-do harness contracts drift --tool security
./agent-do harness bounds drift --tool security
bin/gen-tools-doc --check
```

Tests cover official Maven JSON shapes, Gradle graph shapes, and end-to-end CLI
behavior with executable build/scanner doubles. This execution environment has
Java but no Maven, Gradle, or OSV-Scanner, and its shell network proxy is
unreachable. A real Spring Boot Maven/Gradle run and live advisory lookup have
not been verified here. Run the commands above on your machine before relying
on the results operationally.

References: [Maven JSON tree format](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html),
[Gradle resolution graph](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/result/ResolutionResult.html),
[Gradle initialization scripts](https://docs.gradle.org/current/userguide/init_scripts.html),
and [OSV source/SBOM scanning](https://google.github.io/osv-scanner/usage/scan-source).
