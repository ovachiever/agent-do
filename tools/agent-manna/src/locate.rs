//! Read-only machine-registry lookup. No board derivation, locks or recovery.
use std::collections::{BTreeMap, HashSet};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
pub struct Match {
    pub name: String,
    pub slug: String,
    pub root: String,
    #[serde(rename = "type")]
    pub issue_type: crate::issue::IssueType,
    pub status: crate::issue::IssueStatus,
    pub title: String,
}

#[derive(Debug, Serialize)]
pub struct Unreadable {
    pub root: String,
    pub reason: String,
}

#[derive(Debug, Serialize)]
pub struct Located {
    pub id: String,
    pub matches: Vec<Match>,
    pub unreadable: Vec<Unreadable>,
    pub absent: Vec<String>,
    pub examined: usize,
}

#[derive(Deserialize)]
struct Registry {
    boards: BTreeMap<String, Registration>,
}

#[derive(Deserialize)]
struct Registration {
    path: PathBuf,
}

#[derive(Deserialize)]
struct Row {
    id: String,
    title: String,
    status: crate::issue::IssueStatus,
    #[serde(rename = "type", default)]
    issue_type: crate::issue::IssueType,
}

pub fn valid_id(id: &str) -> bool {
    id.strip_prefix("mn-").is_some_and(|suffix| {
        suffix.len() >= 6
            && suffix
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    })
}

pub fn locate(id: &str) -> Result<Located, String> {
    let home = std::env::var_os("AGENT_DO_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".agent-do")))
        .ok_or("Cannot locate the Manna registry: AGENT_DO_HOME and HOME are unset")?;
    locate_in(id, &home.join("manna/serve/boards.json"))
}

pub fn locate_in(id: &str, registry_path: &Path) -> Result<Located, String> {
    if !valid_id(id) {
        return Err(
            "Invalid Manna id: expected mn- followed by at least six lowercase hex digits".into(),
        );
    }
    let metadata = std::fs::metadata(registry_path)
        .map_err(|e| format!("Cannot read registry {}: {e}", registry_path.display()))?;
    if !metadata.is_file() {
        return Err(format!(
            "Cannot read registry {}: not a regular file",
            registry_path.display()
        ));
    }
    let registry: Registry = serde_json::from_reader(
        std::fs::File::open(registry_path)
            .map_err(|e| format!("Cannot read registry {}: {e}", registry_path.display()))?,
    )
    .map_err(|e| format!("Cannot decode registry {}: {e}", registry_path.display()))?;
    if registry
        .boards
        .values()
        .any(|entry| !entry.path.is_absolute())
    {
        return Err("Invalid Manna registry: every board path must be absolute".into());
    }
    let mut result = Located {
        id: id.into(),
        matches: vec![],
        unreadable: vec![],
        absent: vec![],
        examined: 0,
    };
    let mut seen = HashSet::new();
    for (slug, registration) in registry.boards {
        // Registry aliases of one physical checkout are not duplicate holders.
        let root = registration
            .path
            .canonicalize()
            .unwrap_or(registration.path);
        if !seen.insert(root.clone()) {
            continue;
        }
        result.examined += 1;
        let root_text = root.to_string_lossy().into_owned();
        let rows_path = root.join(".manna/issues.jsonl");
        let read = (|| -> Result<Option<Row>, String> {
            let metadata = match std::fs::metadata(&rows_path) {
                Ok(value) => value,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    result.absent.push(root_text.clone());
                    return Ok(None);
                }
                Err(e) => return Err(e.to_string()),
            };
            // Never block on a FIFO/device accidentally registered as a ledger.
            if !metadata.is_file() {
                return Err("issues.jsonl is not a regular file".into());
            }
            let file = std::fs::File::open(&rows_path).map_err(|e| e.to_string())?;
            let mut found = None;
            for (index, line) in BufReader::new(file).lines().enumerate() {
                let line = line.map_err(|e| format!("line {}: {e}", index + 1))?;
                if line.trim().is_empty() {
                    continue;
                }
                let row: Row =
                    serde_json::from_str(&line).map_err(|e| format!("line {}: {e}", index + 1))?;
                if row.id == id {
                    if found.is_some() {
                        return Err(format!("duplicate issue row for {id}"));
                    }
                    found = Some(row);
                }
            }
            Ok(found)
        })();
        match read {
            Ok(Some(row)) => result.matches.push(Match {
                name: root
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned(),
                slug,
                root: root_text,
                issue_type: row.issue_type,
                status: row.status,
                title: row.title,
            }),
            Ok(None) => {}
            Err(reason) => result.unreadable.push(Unreadable {
                root: root_text,
                reason,
            }),
        }
    }
    Ok(result)
}
