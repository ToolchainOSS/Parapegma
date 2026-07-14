# Spark anonymous research telemetry

The independent Spark prototype is deliberately **account-free**. It must not
invoke Flow registration, login, passkeys, project membership, or email. Its
research identity is a pseudonymous browser installation, not an authentication
or authorization mechanism.

## Identity strategy

Every Spark request contains four client-generated fields:

1. A random UUID stored under `flow.spark.research-installation-id.v1` in
   `localStorage`. This is the primary longitudinal anchor for one browser
   installation.
2. A ThumbmarkJS hash generated locally without a ThumbmarkJS API key. Only the
   resulting hash is sent to Flow; Thumbmark components are not sent to any
   third party.
3. ThumbmarkJS version, browser locale, and IANA timezone as diagnostic context
   for fingerprint-stability analysis.
4. A per-flow UUID and a unique client-event UUID, so flows can be reconstructed
   and retries do not duplicate analysis rows.

The server requires `SPARK_IDENTITY_HMAC_KEY` to HMAC the installation ID and
fingerprint immediately. It stores neither raw value nor logs either value.
Use one stable secret for a study; rotating it prevents future requests from
linking to past participants.

Clearing site data creates a new installation identity. A changed or shared
fingerprint never automatically merges participants: fingerprint observations
remain separate so researchers can quantify instability and potential
collisions before deciding whether a stronger identity technique is needed.

## Stored records

| Table | Purpose |
| --- | --- |
| `spark_participants` | One row per HMACed browser-local installation ID. |
| `spark_fingerprint_observations` | HMACed fingerprint observations, version, locale, timezone, first/last seen, and count. |
| `spark_interactions` | Immutable condition-scoped events, including generated cards, selection, timer outcome, feedback, cue, and final ratings. |

`POST /spark/generate` persists an idempotent `generation_succeeded` event with
the researcher-relevant request context and response cards. It intentionally
excludes identity inputs from the stored payload.

`POST /spark/events` accepts a strict discriminated event union:

- `flow_started`
- `intake_answered`
- `frame_selected`
- `card_selected`
- `timer_finished`
- `feedback_submitted`
- `cue_selected`
- `condition_completed`

This provides condition-level evidence for delivery, choice, personalization,
selection, completion, perceived fit, action clarity, and willingness to try.

## Analysis considerations

- Treat the browser installation as the longitudinal unit for the initial
  study, not as a person-level identity.
- Measure fingerprint stability as distinct HMACed fingerprints per
  `spark_participants.id`, and potential duplication as distinct participants
  per HMACed fingerprint.
- Compare conditions only after accounting for repeated flows from the same
  installation and the flow completion rate.
- Do not use pseudonymous Spark identity for access control, the Flow
  conversation engine, invitations, memberships, or Web Push.
- Retention, consent language, and export/deletion processes remain study-level
  governance decisions and must be approved before collecting participant data.
