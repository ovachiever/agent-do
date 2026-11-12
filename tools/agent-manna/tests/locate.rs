use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{Duration, Instant};

struct Estate {
    temp: tempfile::TempDir,
    boards: serde_json::Map<String, Value>,
}

impl Estate {
    fn new() -> Self {
        Self {
            temp: tempfile::tempdir().unwrap(),
            boards: Default::default(),
        }
    }
    fn board(&mut self, name: &str, rows: &[Value]) -> PathBuf {
        let root = self.temp.path().join(name);
        fs::create_dir_all(root.join(".manna")).unwrap();
        fs::write(
            root.join(".manna/issues.jsonl"),
            rows.iter()
                .map(|row| format!("{row}\n"))
                .collect::<String>(),
        )
        .unwrap();
        self.boards.insert(name.into(), json!({"path":root}));
        root.canonicalize().unwrap()
    }
    fn registry(&self) -> PathBuf {
        let path = self.temp.path().join("manna/serve/boards.json");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, json!({"boards": self.boards}).to_string()).unwrap();
        path
    }
    fn run(&self, args: &[&str], cwd: Option<&Path>) -> Output {
        Command::new(env!("CARGO_BIN_EXE_manna-core"))
            .args(args)
            .env("AGENT_DO_HOME", self.temp.path())
            .current_dir(cwd.unwrap_or(self.temp.path()))
            .output()
            .unwrap()
    }
    fn locate(&self, id: &str) -> Value {
        let output = self.run(&["locate", id, "--json"], None);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        serde_json::from_slice(&output.stdout).unwrap()
    }
}

fn row(id: &str) -> Value {
    json!({"id":id,"title":"A located item","status":"done"})
}

#[test]
fn one_two_and_zero_holders_have_complete_metadata_without_writes() {
    let mut estate = Estate::new();
    let first = estate.board("one", &[row("mn-abcdef")]);
    let registry = estate.registry();
    let before = fs::read(&registry).unwrap();
    let result = estate.locate("mn-abcdef");
    assert_eq!(
        result["matches"],
        json!([{"name":"one","slug":"one","root":first,"title":"A located item","status":"done","type":"item"}])
    );
    assert_eq!(result["examined"], 1);
    assert_eq!(fs::read(registry).unwrap(), before);
    assert_eq!(fs::read_dir(estate.temp.path()).unwrap().count(), 2);
    assert_eq!(fs::read_dir(first.join(".manna")).unwrap().count(), 1);
    let mut track = row("mn-abcdef");
    track["type"] = json!("track");
    estate.board("two", &[track]);
    estate.registry();
    let two = estate.locate("mn-abcdef");
    assert_eq!(two["matches"].as_array().unwrap().len(), 2);
    assert_eq!(two["matches"][1]["type"], "track");
    assert_eq!(estate.locate("mn-000000")["matches"], json!([]));
}

#[test]
fn unreadable_and_absent_boards_do_not_veto_a_holder() {
    let mut estate = Estate::new();
    estate.board("holder", &[row("mn-abcdef")]);
    let broken = estate.board("broken", &[]);
    fs::write(broken.join(".manna/issues.jsonl"), "not json").unwrap();
    let absent = estate.temp.path().join("absent");
    estate
        .boards
        .insert("absent".into(), json!({"path":absent}));
    estate.registry();
    let result = estate.locate("mn-abcdef");
    assert_eq!(result["matches"].as_array().unwrap().len(), 1);
    assert_eq!(result["unreadable"][0]["root"], json!(broken));
    assert!(result["unreadable"][0]["reason"]
        .as_str()
        .unwrap()
        .contains("line 1"));
    assert_eq!(result["absent"], json!([absent]));
    assert_eq!(result["examined"], 3);
}

#[test]
fn non_regular_ledger_is_unreadable_without_opening_it() {
    let mut estate = Estate::new();
    let root = estate.board("fifo", &[]);
    fs::remove_file(root.join(".manna/issues.jsonl")).unwrap();
    assert!(Command::new("mkfifo")
        .arg(root.join(".manna/issues.jsonl"))
        .status()
        .unwrap()
        .success());
    estate.registry();
    let result = estate.locate("mn-abcdef");
    assert_eq!(
        result["unreadable"][0]["reason"],
        "issues.jsonl is not a regular file"
    );
}

#[test]
fn invalid_id_and_missing_or_malformed_registry_fail_in_json() {
    let estate = Estate::new();
    for id in [
        "mn-xbcdef",
        "mn-ABCDEF",
        "mn-abcde",
        "../mn-abcdef",
        "mn-abcdef\n",
        "mn-abcdef",
    ] {
        let output = estate.run(&["locate", id, "--json"], None);
        assert!(!output.status.success());
        let result: Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(result["success"], false);
    }
    let registry = estate.registry();
    for invalid in ["{", "{}", "{\"boards\":{\"bad\":{\"path\":\"relative\"}}}"] {
        fs::write(&registry, invalid).unwrap();
        assert!(!estate
            .run(&["locate", "mn-abcdef", "--json"], None)
            .status
            .success());
    }
}

#[test]
fn registry_aliases_do_not_duplicate_a_board() {
    let mut estate = Estate::new();
    let root = estate.board("one", &[row("mn-abcdef")]);
    estate.boards.insert("alias".into(), json!({"path": root}));
    estate.registry();
    let result = estate.locate("mn-abcdef");
    assert_eq!(result["examined"], 1);
    assert_eq!(result["matches"].as_array().unwrap().len(), 1);
}

#[test]
fn thirty_five_boards_with_slow_derivation_and_failure_locate_under_two_seconds() {
    let mut estate = Estate::new();
    for i in 0..35 {
        let rows = if i == 34 {
            vec![row("mn-abcdef")]
        } else {
            vec![row("mn-000000"); 200]
        };
        let root = estate.board(&format!("board-{i:02}"), &rows);
        // A derivation's drift input would block, but locating never opens it.
        assert!(Command::new("mkfifo")
            .arg(root.join(".manna/drift.yaml"))
            .status()
            .unwrap()
            .success());
        if i == 17 {
            fs::write(root.join(".manna/issues.jsonl"), "broken").unwrap();
        }
    }
    estate.registry();
    for (id, matches) in [("mn-abcdef", 1), ("mn-111111", 0)] {
        let start = Instant::now();
        let result = estate.locate(id);
        let elapsed = start.elapsed();
        println!("35-board lookup {id}: {elapsed:?}");
        assert!(elapsed < Duration::from_secs(2), "{elapsed:?}");
        assert_eq!(result["examined"], 35);
        assert_eq!(result["matches"].as_array().unwrap().len(), matches);
        assert_eq!(result["unreadable"].as_array().unwrap().len(), 1);
    }
}

#[test]
fn show_pointer_uses_the_same_lookup() {
    let mut estate = Estate::new();
    let origin = estate.board("origin", &[]);
    // MannaStore's initialized marker, without invoking any mutation.
    fs::write(origin.join(".manna/sessions.jsonl"), "").unwrap();
    estate.board("holder", &[row("mn-abcdef")]);
    estate.registry();
    let result = estate.run(&["show", "mn-abcdef", "--json"], Some(&origin));
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stdout).contains("it lives on holder"),
        "{}",
        String::from_utf8_lossy(&result.stdout)
    );
}

#[test]
fn non_regular_registry_refuses_without_opening_it() {
    let estate = Estate::new();
    let registry = estate.registry();
    fs::remove_file(&registry).unwrap();
    assert!(Command::new("mkfifo")
        .arg(&registry)
        .status()
        .unwrap()
        .success());
    let output = estate.run(&["locate", "mn-abcdef", "--json"], None);
    assert!(!output.status.success());
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert!(result["error"]
        .as_str()
        .unwrap()
        .contains("not a regular file"));
}
