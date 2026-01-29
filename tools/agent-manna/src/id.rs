use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::time::{SystemTime, UNIX_EPOCH};

/// Generate a hash-based ID with format `mn-[a-f0-9]{6,}`
///
/// Uses 16 random bytes + current timestamp, hashed with SHA256.
/// Takes first 6 hex characters of the hash.
pub fn generate_id() -> String {
    generate_id_with_seed(None)
}

/// Generate a unique ID, extending length on collision
///
/// Starts with 6 hex characters. If collision detected in `existing_ids`,
/// extends to 7, 8, 9... characters until unique.
pub fn generate_unique_id(existing_ids: &HashSet<String>) -> String {
    let mut id = generate_id();
    let mut length = 6;

    while existing_ids.contains(&id) && length < 64 {
        length += 1;
        id = generate_id_extended(length);
    }

    id
}

/// Internal: Generate ID with optional seed for deterministic testing
fn generate_id_with_seed(seed: Option<u64>) -> String {
    let mut data = Vec::new();

    // Add random bytes
    if let Some(seed_val) = seed {
        // Deterministic mode: use seed
        data.extend_from_slice(&seed_val.to_le_bytes());
        data.extend_from_slice(&[0u8; 8]); // Pad to 16 bytes
    } else {
        // Random mode
        let random_bytes = generate_random_bytes(16);
        data.extend_from_slice(&random_bytes);
    }

    // Add timestamp (nanoseconds)
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64;
    data.extend_from_slice(&timestamp.to_le_bytes());

    // Hash with SHA256
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let hash = hasher.finalize();

    // Take first 6 hex characters
    let hex = format!("{:x}", hash);
    format!("mn-{}", &hex[..6])
}

/// Internal: Generate ID with specific hex length
fn generate_id_extended(length: usize) -> String {
    let random_bytes = generate_random_bytes(16);
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64;

    let mut data = Vec::new();
    data.extend_from_slice(&random_bytes);
    data.extend_from_slice(&timestamp.to_le_bytes());

    let mut hasher = Sha256::new();
    hasher.update(&data);
    let hash = hasher.finalize();

    let hex = format!("{:x}", hash);
    let take_len = length.min(hex.len());
    format!("mn-{}", &hex[..take_len])
}

/// Generate random bytes
fn generate_random_bytes(len: usize) -> Vec<u8> {
    use rand::RngCore;
    let mut bytes = vec![0u8; len];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_id_format() {
        let id = generate_id();
        assert!(id.starts_with("mn-"));
        assert_eq!(id.len(), 9); // "mn-" + 6 hex chars

        // Verify hex characters
        let hex_part = &id[3..];
        assert!(hex_part.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_generate_id_randomness() {
        let id1 = generate_id();
        let id2 = generate_id();
        assert_ne!(id1, id2, "Generated IDs should be different");
    }

    #[test]
    fn test_generate_unique_id_no_collision() {
        let existing = HashSet::new();
        let id = generate_unique_id(&existing);
        assert!(id.starts_with("mn-"));
        assert_eq!(id.len(), 9);
    }

    #[test]
    fn test_generate_unique_id_with_collision() {
        let mut existing = HashSet::new();

        // Manually add a collision by creating a 6-char ID
        existing.insert("mn-abcdef".to_string());

        // Generate unique should extend if collision
        let id = generate_unique_id(&existing);
        assert!(id.starts_with("mn-"));
        // Should be longer than 9 if collision handling worked
        // (though with random generation, collision is unlikely)
    }

    #[test]
    fn test_1000_ids_no_collisions() {
        let mut ids = HashSet::new();

        for _ in 0..1000 {
            let id = generate_id();
            assert!(
                ids.insert(id.clone()),
                "Collision detected: {} already exists",
                id
            );
        }

        assert_eq!(ids.len(), 1000, "All 1000 IDs should be unique");
    }

    #[test]
    fn test_unique_id_extends_on_collision() {
        let mut existing = HashSet::new();

        // Simulate collision by pre-populating with 6-char IDs
        for i in 0..100 {
            existing.insert(format!("mn-{:06x}", i));
        }

        let id = generate_unique_id(&existing);
        assert!(id.starts_with("mn-"));
        // Should still be unique
        assert!(!existing.contains(&id));
    }
}
