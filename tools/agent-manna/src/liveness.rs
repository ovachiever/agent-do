//! Claimant liveness: matching a board claim to coord's presence records.
//!
//! coord is the one source that verifies processes (`kill -0` plus the
//! process start time); manna reads its `peers --all --json`. A record is
//! matched to a claim by exact facts only, strongest first:
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
//! `reconcile --fix` closed a live lane's item.
//!
//! What the records say is decided once, in [`claim_presence`], and only
//! positive evidence counts as death: every bound record `dead` (coord
//! verified the process gone, or tombstoned the session) or `stopped` (the
//! session retired itself). A `stale` record is an aged lease on a process
//! coord could not call dead; a record coord never bound is a claimant coord
//! has said nothing about; a record that contradicts the claim's own facts is
//! an identity nobody can vouch for. None of those is permission to release
//! or close over the claimant (the independent review of ec30858, mn-880173,
//! aged a living claimant's record three days and watched the old cure close
//! its item; a living claimant with no binding went the same way).

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

/// Parse a `peers --json` payload for display. Rows without an agent id or a
/// status are skipped; the `manna` block is read when it is an object (an
/// unbound record, or a coord build that does not render it, carries none).
/// A lifecycle decision reads [`parse_peers_strict`] instead.
pub fn parse_peers(payload: &Value) -> Vec<CoordPeer> {
    payload
        .get("peers")
        .and_then(Value::as_array)
        .map(|peers| peers.iter().filter_map(parse_peer).collect())
        .unwrap_or_default()
}

/// Parse a `peers --json` payload for a lifecycle decision. The payload must
/// carry a `peers` array and every row must carry an agent id and a status,
/// or the whole read is unusable: a row this reader could not read might be
/// the claimant's, and dropping it would show absence where coord said
/// something. Malformed evidence is no evidence of death; the caller fails
/// closed on the error.
pub fn parse_peers_strict(payload: &Value) -> Result<Vec<CoordPeer>, String> {
    let rows = payload
        .get("peers")
        .and_then(Value::as_array)
        .ok_or_else(|| "coord peers payload carries no `peers` array".to_string())?;
    rows.iter()
        .enumerate()
        .map(|(index, row)| {
            parse_peer(row).ok_or_else(|| {
                format!(
                    "coord peers row {} is malformed (no agent_id or status); the read is unusable",
                    index + 1
                )
            })
        })
        .collect()
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
/// verdict. A display vocabulary: a lifecycle decision asks [`is_gone`], and
/// `stale` is not gone either.
pub fn is_live(status: &str) -> bool {
    !matches!(status, "dead" | "stopped" | "stale")
}

/// coord's positive verdicts that a session is gone: `dead` (the process
/// verified gone, or the record tombstoned) and `stopped` (the session retired
/// itself through `coord stop`). Nothing else is evidence of death: `stale`
/// is an aged lease past the idle window on a process coord could not call
/// dead, `idle` a younger one, `unknown` no verdict at all.
pub fn is_gone(status: &str) -> bool {
    matches!(status, "dead" | "stopped")
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

/// The bound records coord still considers live (display vocabulary).
pub fn live_bound<'a, 'b>(bound: &'b [BoundPeer<'a>]) -> Vec<&'b BoundPeer<'a>> {
    bound
        .iter()
        .filter(|record| is_live(&record.peer.status))
        .collect()
}

/// The bound records coord has not positively called gone: these keep the
/// claim, whatever else they are.
pub fn not_gone<'a, 'b>(bound: &'b [BoundPeer<'a>]) -> Vec<&'b BoundPeer<'a>> {
    bound
        .iter()
        .filter(|record| !is_gone(&record.peer.status))
        .collect()
}

/// True when at least one record is bound to the claim and coord has
/// classified every one of them dead or stopped: positive evidence the
/// claimant is gone. One record among them that is anything else keeps the
/// claim, a stale one included; no record at all is inconclusive, never
/// "gone".
pub fn all_gone(bound: &[BoundPeer<'_>]) -> bool {
    !bound.is_empty() && bound.iter().all(|record| is_gone(&record.peer.status))
}

/// What coord's records say about one claim, decided once so every lifecycle
/// reader (the `dead_claim` finding, the landed_open cure's guard, the
/// managed release) rules the same way from the same facts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClaimPresence<'a> {
    /// Every record bound to the claim is dead or stopped: the only verdict
    /// that authorizes a lifecycle repair over the claimant.
    Gone(Vec<BoundPeer<'a>>),
    /// At least one bound record is not positively gone (active, idle, stale,
    /// unknown). Carries every bound record; [`not_gone`] picks the ones that
    /// keep the claim.
    Present(Vec<BoundPeer<'a>>),
    /// No record is bound to the claim. coord has said nothing about this
    /// claimant: absence is not evidence of death.
    Unseen,
    /// A bound record contradicts the claim's own facts: a record wearing the
    /// claimant's label or agent id under a different proof, or carrying the
    /// claim's proof under a different label. Which process holds the claim
    /// cannot be told, so no lifecycle repair may act on it. Each entry names
    /// the record and the contradiction.
    Ambiguous(Vec<String>),
}

impl ClaimPresence<'_> {
    /// `gone`, `present`, `unseen`, or `ambiguous`.
    pub fn name(&self) -> &'static str {
        match self {
            ClaimPresence::Gone(_) => "gone",
            ClaimPresence::Present(_) => "present",
            ClaimPresence::Unseen => "unseen",
            ClaimPresence::Ambiguous(_) => "ambiguous",
        }
    }
}

/// Rule on a claim from coord's complete records (`peers --all`: a read that
/// leaves stale records out shows absence where coord said "aged").
pub fn claim_presence<'a>(
    peers: &'a [CoordPeer],
    claimed_by: &str,
    claim_token_hash: Option<&str>,
) -> ClaimPresence<'a> {
    let bound = peers_bound_to_claim(peers, claimed_by, claim_token_hash);
    if bound.is_empty() {
        return ClaimPresence::Unseen;
    }
    let proof = claim_token_hash
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let contradictions: Vec<String> = bound
        .iter()
        .filter_map(|record| {
            let peer = record.peer;
            match record.binding {
                // The claim's proof under another label: one secret, two names.
                Binding::Proof => match peer.manna_session.as_deref() {
                    Some(label) if label != claimed_by => Some(format!(
                        "{} {} carries the claim's proof under the label {}, not {}",
                        peer.agent_id, peer.status, label, claimed_by
                    )),
                    _ => None,
                },
                // The claimant's label or agent id under another proof: a
                // different process wearing the claimant's name.
                Binding::Label | Binding::AgentId => {
                    if let (Some(expected), Some(found)) = (proof, peer.manna_proof.as_deref()) {
                        if found != expected {
                            return Some(format!(
                                "{} {} wears the claimant label {} under a different proof",
                                peer.agent_id, peer.status, claimed_by
                            ));
                        }
                    }
                    match (record.binding, peer.manna_session.as_deref()) {
                        (Binding::AgentId, Some(label)) if label != claimed_by => Some(format!(
                            "{} {} is the claimant label as an agent id but is bound to the manna label {}",
                            peer.agent_id, peer.status, label
                        )),
                        _ => None,
                    }
                }
            }
        })
        .collect();
    if !contradictions.is_empty() {
        return ClaimPresence::Ambiguous(contradictions);
    }
    if all_gone(&bound) {
        ClaimPresence::Gone(bound)
    } else {
        ClaimPresence::Present(bound)
    }
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
    fn strict_parse_refuses_a_read_it_cannot_fully_read() {
        // The same rows: the lenient parser drops two, the strict one refuses
        // the read and names the first row it could not read.
        let payload = json!({"peers": [
            {"agent_id": "session-31022d9c53c9", "status": "active"},
            {"status": "active"},
            {"agent_id": "session-nostatus"}
        ]});
        let error = parse_peers_strict(&payload).unwrap_err();
        assert!(
            error.contains("row 2") && error.contains("malformed"),
            "{error}"
        );
        // No peers array at all is not an empty estate.
        let error = parse_peers_strict(&json!({"ok": true})).unwrap_err();
        assert!(error.contains("no `peers` array"), "{error}");
        // A clean payload parses to the same rows the lenient parser gives.
        let clean = json!({"peers": [
            {"agent_id": "session-a", "status": "stale", "manna": {"session": "claude-a", "proof": "sha256:a"}},
            {"agent_id": "session-b", "status": "dead"}
        ]});
        assert_eq!(parse_peers_strict(&clean).unwrap(), parse_peers(&clean));
        assert!(parse_peers_strict(&json!({"peers": []}))
            .unwrap()
            .is_empty());
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
        assert_eq!(not_gone(&bound).len(), 1);
    }

    #[test]
    fn liveness_vocabulary() {
        for status in ["active", "idle", "unknown"] {
            assert!(
                is_live(status),
                "{status} is not permission to act over the claimant"
            );
            assert!(!is_gone(status));
        }
        for status in ["dead", "stopped"] {
            assert!(!is_live(status));
            assert!(is_gone(status), "{status} is coord's positive verdict");
        }
        // Stale is neither: an aged lease past the idle window on a process
        // coord could not call dead. Not live for display, not gone for a
        // lifecycle decision.
        assert!(!is_live("stale"));
        assert!(!is_gone("stale"));
        let gone = vec![
            peer("session-a", "dead", None, Some("sha256:g")),
            peer("session-b", "stopped", None, Some("sha256:g")),
        ];
        let bound = peers_bound_to_claim(&gone, "claude-g", Some("sha256:g"));
        assert!(all_gone(&bound));
        assert!(live_bound(&bound).is_empty());
        assert!(not_gone(&bound).is_empty());
        // No record at all is inconclusive, never "gone".
        assert!(!all_gone(&[]));
    }

    #[test]
    fn positive_evidence_only_decides_gone() {
        // The review's aged claimant: a proof-bound record whose lease aged
        // three days while the process stayed alive. Stale keeps the claim.
        let aged = vec![peer(
            "session-d9c459ef4559",
            "stale",
            Some("claude-d9c459ef4559496f"),
            Some("sha256:aged"),
        )];
        let bound = peers_bound_to_claim(&aged, "claude-d9c459ef4559496f", Some("sha256:aged"));
        assert!(!all_gone(&bound), "an aged lease is not death");
        assert_eq!(not_gone(&bound).len(), 1);
        assert!(
            live_bound(&bound).is_empty(),
            "stale is not live either; the display vocabulary says so"
        );
        // One stale record beside a dead twin still keeps the claim.
        let mixed = vec![
            peer("session-twin-dead", "dead", None, Some("sha256:m")),
            peer("session-twin-aged", "stale", None, Some("sha256:m")),
        ];
        assert!(!all_gone(&peers_bound_to_claim(
            &mixed,
            "claude-m",
            Some("sha256:m")
        )));
        // Idle and unknown keep it too.
        for status in ["idle", "unknown", "active"] {
            let rows = vec![peer("session-k", status, None, Some("sha256:k"))];
            assert!(!all_gone(&peers_bound_to_claim(
                &rows,
                "claude-k",
                Some("sha256:k")
            )));
        }
    }

    #[test]
    fn claim_presence_rules_once_for_every_reader() {
        let peers = vec![
            // dead + stopped twins: positively gone
            peer(
                "session-gone-a",
                "dead",
                Some("claude-gone"),
                Some("sha256:gone"),
            ),
            peer("session-gone-b", "stopped", None, Some("sha256:gone")),
            // the aged living claimant
            peer(
                "session-aged",
                "stale",
                Some("claude-aged"),
                Some("sha256:aged"),
            ),
            // a dead record beside an idle one
            peer("session-half-a", "dead", None, Some("sha256:half")),
            peer("session-half-b", "idle", None, Some("sha256:half")),
            // the claimant label worn by another process under another proof
            peer(
                "session-impostor",
                "active",
                Some("claude-worn"),
                Some("sha256:someone-else"),
            ),
            // the claim's proof under another label
            peer(
                "session-alias",
                "active",
                Some("claude-other-name"),
                Some("sha256:shared"),
            ),
            // a thread id as agent id, bound to a different manna label
            peer(
                "codex-thread0000000001",
                "active",
                Some("codex-elsewhere00000001"),
                None,
            ),
            // a thread id as agent id with no binding at all
            peer("codex-thread0000000002", "dead", None, None),
        ];
        match claim_presence(&peers, "claude-gone", Some("sha256:gone")) {
            ClaimPresence::Gone(bound) => assert_eq!(bound.len(), 2),
            other => panic!("dead and stopped twins are gone, got {}", other.name()),
        }
        match claim_presence(&peers, "claude-aged", Some("sha256:aged")) {
            ClaimPresence::Present(bound) => {
                assert_eq!(bound.len(), 1);
                assert_eq!(not_gone(&bound)[0].peer.status, "stale");
            }
            other => panic!("a stale record keeps the claim, got {}", other.name()),
        }
        match claim_presence(&peers, "claude-half", Some("sha256:half")) {
            ClaimPresence::Present(bound) => {
                assert_eq!(bound.len(), 2);
                assert_eq!(not_gone(&bound)[0].peer.agent_id, "session-half-b");
            }
            other => panic!("one idle twin keeps the claim, got {}", other.name()),
        }
        assert_eq!(
            claim_presence(&peers, "claude-nobody", Some("sha256:nobody")),
            ClaimPresence::Unseen,
            "no bound record is unseen, never gone"
        );
        match claim_presence(&peers, "claude-worn", Some("sha256:mine")) {
            ClaimPresence::Ambiguous(reasons) => {
                assert_eq!(reasons.len(), 1);
                assert!(
                    reasons[0].contains("session-impostor")
                        && reasons[0].contains("under a different proof"),
                    "{reasons:?}"
                );
            }
            other => panic!("a worn label is ambiguous, got {}", other.name()),
        }
        match claim_presence(&peers, "claude-my-name", Some("sha256:shared")) {
            ClaimPresence::Ambiguous(reasons) => {
                assert!(
                    reasons[0].contains("session-alias")
                        && reasons[0].contains("claude-other-name"),
                    "{reasons:?}"
                );
            }
            other => panic!(
                "a shared proof under another label is ambiguous, got {}",
                other.name()
            ),
        }
        match claim_presence(&peers, "codex-thread0000000001", None) {
            ClaimPresence::Ambiguous(reasons) => {
                assert!(
                    reasons[0].contains("codex-elsewhere00000001"),
                    "{reasons:?}"
                );
            }
            other => panic!(
                "an agent id bound to another label is ambiguous, got {}",
                other.name()
            ),
        }
        // An agent-id match with no binding and no proof to compare is not a
        // contradiction; dead, it is gone.
        match claim_presence(&peers, "codex-thread0000000002", None) {
            ClaimPresence::Gone(bound) => assert_eq!(bound[0].binding, Binding::AgentId),
            other => panic!("got {}", other.name()),
        }
        // A legacy row with no proof matches by label alone and cannot be
        // contradicted on proof.
        match claim_presence(&peers, "claude-worn", None) {
            ClaimPresence::Present(_) => {}
            other => panic!("a proofless row is ruled on presence, got {}", other.name()),
        }
    }
}
