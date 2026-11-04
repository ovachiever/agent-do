//! Claimant liveness: matching a board claim to coord's presence records.
//!
//! coord is the one source that verifies processes (`kill -0` plus the
//! process start time); manna reads its `peers --json`. A record is matched
//! to a claim by exact facts only, strongest first:
//!
//! 1. the record's bound Manna proof equals the row's `claim_token_hash`
//!    (`coord touch` asks `manna identity` in the worker's own process and
//!    stores the digest on the record);
//! 2. the record's bound Manna label equals the row's `claimed_by`;
//! 3. the record's agent id is the claimant label verbatim (thread-derived
//!    identities, where coord and manna spell one label).
//!
//! Nothing is derived from the label. Before mn-4e7229 the reconcile guard
//! looked a claimant up as `session-` plus the label's first sixteen
//! alphanumerics, so `claude-31022d9c53c942eb` became
//! `session-claude31022d9c53` while coord named that session
//! `session-31022d9c53c9`: no match, the miss read as the orphan wedge, and
//! `reconcile --fix` closed a live lane's item. A record coord never bound
//! is absent here, honestly; the caller decides what absence means.

use std::collections::HashMap;

use serde_json::Value;

/// One coord presence record as `peers --json` renders it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CoordPeer {
    pub agent_id: String,
    /// coord's classification: `active`, `idle`, `stale`, `dead`, `stopped`,
    /// or `unknown`.
    pub status: String,
    /// `manna.session` on the record: the Manna label the session's own
    /// process reported.
    pub manna_session: Option<String>,
    /// `manna.proof` on the record: the ownership digest that process
    /// reported, equal to `claim_token_hash` on every row it claims.
    pub manna_proof: Option<String>,
}

/// Which exact fact matched a record to a claim. Ordered strongest first.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Binding {
    /// `manna.proof` equals the row's `claim_token_hash`.
    Proof,
    /// `manna.session` equals the row's `claimed_by`.
    Label,
    /// The coord agent id is the claimant label verbatim.
    AgentId,
}

impl Binding {
    pub fn describe(self) -> &'static str {
        match self {
            Binding::Proof => "bound by claim proof",
            Binding::Label => "bound by manna label",
            Binding::AgentId => "agent id is the claimant label",
        }
    }
}

/// A record matched to a claim, with the fact that matched it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundPeer<'a> {
    pub peer: &'a CoordPeer,
    pub binding: Binding,
}

impl BoundPeer<'_> {
    /// `session-31022d9c53c9 active (bound by claim proof)`
    pub fn describe(&self) -> String {
        format!(
            "{} {} ({})",
            self.peer.agent_id,
            self.peer.status,
            self.binding.describe()
        )
    }
}

/// Parse a `peers --json` payload. Rows without an agent id or a status are
/// skipped; the `manna` block is read when it is an object (an unbound record,
/// or a coord build that does not render it, carries none).
pub fn parse_peers(payload: &Value) -> Vec<CoordPeer> {
    payload
        .get("peers")
        .and_then(Value::as_array)
        .map(|peers| peers.iter().filter_map(parse_peer).collect())
        .unwrap_or_default()
}

/// One `peers --json` row.
pub fn parse_peer(peer: &Value) -> Option<CoordPeer> {
    let agent_id = peer.get("agent_id")?.as_str()?.to_string();
    let status = peer.get("status")?.as_str()?.to_string();
    let manna = peer.get("manna").filter(|value| value.is_object());
    let field = |name: &str| {
        manna
            .and_then(|block| block.get(name))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
    };
    Some(CoordPeer {
        agent_id,
        status,
        manna_session: field("session"),
        manna_proof: field("proof"),
    })
}

/// agent id -> status, for readers that need only coord's classification.
pub fn statuses_by_agent(peers: &[CoordPeer]) -> HashMap<String, String> {
    peers
        .iter()
        .map(|peer| (peer.agent_id.clone(), peer.status.clone()))
        .collect()
}

/// coord's own notion of a live record: anything it has not classified dead,
/// stopped, or stale. `active` is a current lease; `idle` is an aged lease on
/// a process coord could not call dead; `unknown` is a record with no
/// verdict. None of those is permission to act over the claimant.
pub fn is_live(status: &str) -> bool {
    !matches!(status, "dead" | "stopped" | "stale")
}

/// Every record bound to the claim, strongest binding first, then by agent
/// id. Exact facts only: nothing is respelled or shortened to find a match.
pub fn peers_bound_to_claim<'a>(
    peers: &'a [CoordPeer],
    claimed_by: &str,
    claim_token_hash: Option<&str>,
) -> Vec<BoundPeer<'a>> {
    let proof = claim_token_hash
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let mut bound: Vec<BoundPeer<'a>> = peers
        .iter()
        .filter_map(|peer| {
            let binding = if proof.is_some() && peer.manna_proof.as_deref() == proof {
                Binding::Proof
            } else if peer.manna_session.as_deref() == Some(claimed_by) {
                Binding::Label
            } else if peer.agent_id == claimed_by {
                Binding::AgentId
            } else {
                return None;
            };
            Some(BoundPeer { peer, binding })
        })
        .collect();
    bound.sort_by(|left, right| {
        left.binding
            .cmp(&right.binding)
            .then_with(|| left.peer.agent_id.cmp(&right.peer.agent_id))
    });
    bound
}

/// The bound records coord still considers live.
pub fn live_bound<'a, 'b>(bound: &'b [BoundPeer<'a>]) -> Vec<&'b BoundPeer<'a>> {
    bound
        .iter()
        .filter(|record| is_live(&record.peer.status))
        .collect()
}

/// True when at least one record is bound to the claim and coord has
/// classified every one of them dead, stopped, or stale. One live record
/// among dead twins keeps the claim alive; no record at all is inconclusive.
pub fn all_gone(bound: &[BoundPeer<'_>]) -> bool {
    !bound.is_empty() && bound.iter().all(|record| !is_live(&record.peer.status))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn peer(agent_id: &str, status: &str, session: Option<&str>, proof: Option<&str>) -> CoordPeer {
        CoordPeer {
            agent_id: agent_id.to_string(),
            status: status.to_string(),
            manna_session: session.map(str::to_string),
            manna_proof: proof.map(str::to_string),
        }
    }

    #[test]
    fn parses_bound_and_unbound_rows() {
        let payload = json!({"peers": [
            {"agent_id": "session-31022d9c53c9", "status": "active",
             "manna": {"session": "claude-31022d9c53c942eb", "proof": "sha256:abc", "bound_at": "2026-11-04T15:54:53Z"}},
            {"agent_id": "session-7f5a18c8c2da", "status": "idle", "manna": null},
            {"agent_id": "codex-aaaaaaaa11114222", "status": "dead"},
            {"status": "active"},
            {"agent_id": "session-nostatus"}
        ]});
        let peers = parse_peers(&payload);
        assert_eq!(peers.len(), 3, "rows without an id or a status are skipped");
        assert_eq!(
            peers[0],
            peer(
                "session-31022d9c53c9",
                "active",
                Some("claude-31022d9c53c942eb"),
                Some("sha256:abc")
            )
        );
        assert_eq!(peers[1], peer("session-7f5a18c8c2da", "idle", None, None));
        assert_eq!(peers[2], peer("codex-aaaaaaaa11114222", "dead", None, None));
        assert_eq!(
            statuses_by_agent(&peers).get("codex-aaaaaaaa11114222"),
            Some(&"dead".to_string())
        );
        assert!(parse_peers(&json!({})).is_empty());
    }

    #[test]
    fn matches_by_binding_never_by_respelling_the_label() {
        let peers = vec![
            peer(
                "session-31022d9c53c9",
                "active",
                Some("claude-31022d9c53c942eb"),
                Some("sha256:live"),
            ),
            peer("codex-aaaaaaaa11114222", "active", None, None),
            peer("session-019d79125a477c01", "dead", None, None),
            peer("session-claude31022d9c53", "active", None, None),
        ];
        // The hook pairing: coord keeps twelve hex of the session id, manna's
        // label sixteen. Found by the stored proof.
        let bound = peers_bound_to_claim(&peers, "claude-31022d9c53c942eb", Some("sha256:live"));
        assert_eq!(bound.len(), 1);
        assert_eq!(bound[0].binding, Binding::Proof);
        assert_eq!(bound[0].peer.agent_id, "session-31022d9c53c9");
        assert_eq!(
            bound[0].describe(),
            "session-31022d9c53c9 active (bound by claim proof)"
        );
        // A row whose proof coord never saw still matches by the bound label.
        let bound = peers_bound_to_claim(&peers, "claude-31022d9c53c942eb", Some("sha256:other"));
        assert_eq!(bound.len(), 1);
        assert_eq!(bound[0].binding, Binding::Label);
        // Thread-derived identities spell one label in both tools.
        let bound = peers_bound_to_claim(&peers, "codex-aaaaaaaa11114222", None);
        assert_eq!(bound.len(), 1);
        assert_eq!(bound[0].binding, Binding::AgentId);
        // A raw session uuid is not respelled into `session-<16 hex>`: that
        // derivation named nothing coord uses, so the record is not a match.
        assert!(
            peers_bound_to_claim(&peers, "019d7912-5a47-7c01-b9ae-90ac2060a27e", None).is_empty()
        );
        // Nor is a claude label respelled into `session-claude...`, even when
        // a record of that exact spelling happens to exist.
        let unbound = vec![
            peer("session-31022d9c53c9", "active", None, None),
            peer("session-claude31022d9c53", "active", None, None),
        ];
        assert!(
            peers_bound_to_claim(&unbound, "claude-31022d9c53c942eb", Some("sha256:live"))
                .is_empty()
        );
        // An empty or blank proof matches nothing by proof.
        let blank = vec![peer("session-x", "active", None, Some(""))];
        assert!(peers_bound_to_claim(&blank, "claude-x", Some("")).is_empty());
    }

    #[test]
    fn strongest_binding_sorts_first_and_twins_both_count() {
        let peers = vec![
            peer("session-twin-b", "dead", None, Some("sha256:twin")),
            peer("session-twin-a", "active", Some("claude-twin"), None),
            peer("claude-twin", "stopped", None, None),
        ];
        let bound = peers_bound_to_claim(&peers, "claude-twin", Some("sha256:twin"));
        assert_eq!(
            bound
                .iter()
                .map(|record| record.binding)
                .collect::<Vec<_>>(),
            vec![Binding::Proof, Binding::Label, Binding::AgentId]
        );
        let live = live_bound(&bound);
        assert_eq!(live.len(), 1);
        assert_eq!(live[0].peer.agent_id, "session-twin-a");
        assert!(
            !all_gone(&bound),
            "one live record among dead twins keeps the claim alive"
        );
    }

    #[test]
    fn liveness_vocabulary() {
        for status in ["active", "idle", "unknown"] {
            assert!(
                is_live(status),
                "{status} is not permission to act over the claimant"
            );
        }
        for status in ["dead", "stopped", "stale"] {
            assert!(!is_live(status));
        }
        let gone = vec![
            peer("session-a", "dead", None, Some("sha256:g")),
            peer("session-b", "stopped", None, Some("sha256:g")),
        ];
        let bound = peers_bound_to_claim(&gone, "claude-g", Some("sha256:g"));
        assert!(all_gone(&bound));
        assert!(live_bound(&bound).is_empty());
        // No record at all is inconclusive, never "gone".
        assert!(!all_gone(&[]));
    }
}
