# Test strategy

The tests that prove the important parts of the change work. A list too long to read gets approved unread. The section's job is **pre-approval**: the user signs off on the seams and the critical tests here, while the plan is still cheap to change.

## What the section carries

### Seams first

A **seam** is the public boundary a test observes behavior at without reaching inside. Name the seams first — the interfaces, endpoints, and stores this change exposes, and which of them are worth testing at all. Agreeing the seams is how effort lands on the critical paths and the complex logic.

The `tdd` skill holds what makes a test worth keeping; consult it while choosing which tests to list.

The section opens with them — one line per seam, naming the boundary and what it lets a test observe:

> - `POST /resources` — status code and response body
> - `ResourceStore` — what a later read returns
> - CLI `sync` command — exit code and stdout



### Format

One table, with each test at the highest level that can prove its point:


| #   | Level       | Test                              | Proves                                   | Requirements                    |
| --- | ----------- | --------------------------------- | ---------------------------------------- | ------------------------------- |
| 1   | integration | create resource with a fresh slug | 201 and the resource is retrievable      | migrated test DB, authed client |
| 2   | integration | create resource with a taken slug | 409, and the first resource is unchanged | row 1's fixture                 |
| 3   | unit        | slug normalization strips case    | `Foo Bar` and `foo-bar` collide          | none                            |


*Level* is unit, integration, or end-to-end — whichever the change actually calls for. A change that lives entirely behind one seam may be all integration; a pure-logic change may be all unit. *Test* is the scenario in a phrase. *Proves* is the observable, through the seam, that fails when the feature is broken. *Requirements* is what the test needs before it can run: fixtures, seeded data, fakes, environment, the seam it hangs on.

## Floor, not ceiling

The approved tests are a **floor**. Carry that into `master.md` as part of the section, so the implementing agent reads it:

> These are the pre-approved critical tests — a floor, not a ceiling. Implementation writes whatever further tests the code turns out to need.

