# Fixture-only provenance identity

The certificate and private key in this directory are public test material from
the official `contentauth/c2pa-rs` sample directory. The leaf certificate is
marked `OU=FOR TESTING_ONLY`; `proof-pr provenance create` rejects certificates
without that marker. These files must never be used for user artifacts,
production identity, public trust, or credential publication.

Source: <https://github.com/contentauth/c2pa-rs/tree/c2patool-v0.27.16/cli/sample>

The corpus manifest freezes scenario names and expected semantic outcomes. The
test harness generates assets in a temporary directory. Signed bytes are not
byte-deterministic because the C2PA SDK creates fresh instance identifiers; the
source bytes, assertions, scenario transformations, and normalized expected
states are deterministic.
