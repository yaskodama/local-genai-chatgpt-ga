# ReceptionWorkflowZEvolution translation report

- Target language: `ABCL`
- Generations: `5`
- Reviewers: `3`
- Best initial logical view: `predicate_normal_form` score `0.90`
- Contradiction repair: `not_needed`

## Z Specification

```z
[Participant, Reception, RegisteredLedger, SameDayLedger, Materials, Receipt, VALUE]

SystemState
  registered_ledger_contains_pre_registered_partic : VALUE
  same_day_ledger_contains_accepted_same_day_parti : VALUE
  fee_status_is_paid_or_unpaid : VALUE
  materials_are_issued_only_after_acceptance : VALUE
where
    A_participant_must_receive_materials_only_when_r
    A_participant_must_receive_a_receipt_only_when_t
    Rejected_participants_must_not_be_written_to_the
    Every_accepted_same_day_participant_must_be_writ

lookup_participant_in_registered_ledger
  Delta SystemState
  input? : VALUE
  output! : VALUE
  pre lookup_participant_in_registered_ledger_pre
  post lookup_participant_in_registered_ledger_post

collect_fee_for_same_day_participant
  Delta SystemState
  input? : VALUE
  output! : VALUE
  pre collect_fee_for_same_day_participant_pre
  post collect_fee_for_same_day_participant_post

write_accepted_same_day_participant_to_same_day_
  Delta SystemState
  input? : VALUE
  output! : VALUE
  pre write_accepted_same_day_participant_to_same_day__pre
  post write_accepted_same_day_participant_to_same_day__post

issue_materials_and_receipt
  Delta SystemState
  input? : VALUE
  output! : VALUE
  pre issue_materials_and_receipt_pre
  post issue_materials_and_receipt_post

reject_participant_when_fee_is_unpaid
  Delta SystemState
  input? : VALUE
  output! : VALUE
  pre reject_participant_when_fee_is_unpaid_pre
  post reject_participant_when_fee_is_unpaid_post
```

## Checks

### z_schema_review

- ok: `True`
- score: `0.82`
- Z schema is structurally complete

### predicate_normal_form

- ok: `True`
- score: `0.90`
- no direct predicate contradiction found

### state_transition_model

- ok: `True`
- score: `0.75`
- all transitions have enough structure for preservation checks

## Winners

- generation 1: `defensive` score `0.88`
- generation 2: `auditable` score `0.94`
- generation 3: `defensive` score `1.00`
- generation 4: `defensive` score `1.00`
- generation 5: `auditable` score `1.00`
