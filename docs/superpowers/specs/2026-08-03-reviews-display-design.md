# Design — Review display & rating aggregation

Date: 2026-08-03
Branch: `feat/reviews-display`
Phase: G (see `2026-07-31-auth-forms-and-role-routing-design.md`)
Status: approved, implementing

## Problem

The reviews module can create a review (from the order detail page) and list
reviews for a restaurant. Everything customer-facing is missing:

- No aggregation anywhere. A restaurant's rating cannot be read from any
  endpoint.
- `reviewsApi.forRestaurant` exists in the frontend and is never called. No
  screen displays a review, so a review a customer writes is visible to nobody
  except the owner's notification.

## Decisions

- **Ratings are computed on read.** One grouped query, always correct, no
  migration and nothing to invalidate. Reviews exist only for delivered orders,
  so the table stays small. Denormalised counters on `restaurants` are the
  upgrade path if that changes; a drifted rating is worse than a slow one.
- **`average` is `None` for an unreviewed restaurant, never `0.0`.** Zero reads
  and sorts as a terrible restaurant rather than a new one.
- **Reviewers are named "first name + last initial".** Enough to read as a real
  person without publishing a customer's full name to anyone browsing.
- **The breakdown is included** because it comes free from the same grouped
  query, and it is what distinguishes a consistent 4.3 from a polarised one.

## Backend

### `src/modules/reviews/ratings.py` (new)

```python
@dataclass(frozen=True)
class RatingSummary:
    average: float | None      # None when count == 0
    count: int
    breakdown: dict[int, int]  # {5: n, 4: n, 3: n, 2: n, 1: n} — every star present
```

- `summary_for(session, restaurant_ids) -> dict[int, RatingSummary]` — a single
  `SELECT restaurant_id, rating, COUNT(*) ... GROUP BY restaurant_id, rating`.
  Count, average, and breakdown all derive from those rows, so the browse list
  costs one extra query regardless of how many restaurants it returns.
- `summary_for_one(session, restaurant_id) -> RatingSummary`.
- Every requested id appears in the result, with an empty summary when it has no
  reviews, so callers never have to handle a missing key.
- The average is rounded to one decimal place — the precision the UI shows.

### Surfacing it

`restaurants/service.py` gains `attach_ratings(session, restaurants)`, which
asks `reviews.ratings` for the summaries and sets them on the results as
transient attributes the response schemas read. It is called explicitly by the
browse and detail routes — *not* inside `get_restaurant`, which checkout also
uses and has no need for ratings.

This makes `restaurants` depend on `reviews`. There is no cycle: `reviews`
imports `restaurants.models` only, never its service.

| Schema | Gains |
| --- | --- |
| `RestaurantResponse` | `rating_average: float \| None = None`, `review_count: int = 0` |
| `RestaurantDetail` | additionally `rating_breakdown: dict[int, int] = {}` |
| `ReviewRead` | `reviewer_name: str` |

### Review list

`GET /reviews/restaurant/{id}` gains `limit` (default 20, max 100) and `offset`
query parameters; the service already accepted them. It joins `users` to build
the reviewer name through one `display_name(first, last)` helper, so the format
cannot drift between call sites. A missing last name degrades to the first name
alone rather than producing a stray full stop.

The response stays a bare array — the summary travels on the restaurant, so no
existing consumer breaks.

## Frontend

New `frontend/src/reviews/`, mirroring the `payments/` split from phase F:

```
reviews/
  RatingStars.tsx     stars for a value, with an accessible "4.3 out of 5" label
  RatingSummary.tsx   average, count, and the 5→1 breakdown bars
  ReviewsSection.tsx  fetches and renders the list, with Show more
```

- `RestaurantDetailPage` shows the summary beside the restaurant name and the
  reviews section below the menu.
- The browse cards show stars and a review count, or "New" when a restaurant has
  no reviews yet.
- `RatingStars` is presentational and takes a number; `ReviewsSection` owns the
  fetching. That keeps the star rendering testable without any API mocking.

## Test plan

Written test-first per the repository TDD convention.

| Test | Asserts |
| --- | --- |
| `tests/modules/reviews/test_ratings.py` | A single restaurant's average, count, and breakdown; several restaurants summarised together; an unreviewed id returns `None`/0/zeros rather than being absent; the average rounds to one decimal; the breakdown counts each star and lists all five |
| `tests/modules/reviews/test_reviews_display.py` | The list carries `reviewer_name` as "First L."; `limit`/`offset` page the list; the browse response carries `rating_average` and `review_count`; the detail response carries the breakdown; an unreviewed restaurant reports `null`, not `0` |
| `frontend/tests/reviews/RatingStars.test.tsx` | The accessible label states the value out of five; the filled count rounds to the nearest star; a null value renders no rating |
| `frontend/tests/reviews/RatingSummary.test.tsx` | Average and count are shown; each star row shows its count; an unreviewed restaurant shows the empty state instead of zeros |
| `frontend/tests/reviews/ReviewsSection.test.tsx` | Reviews render with name, rating, and comment; a comment-less review still renders; Show more requests the next page and appends; the empty state invites the first review |
| `frontend/tests/pages/RestaurantsPage.test.tsx` (extend) | A rated card shows its rating; an unrated card shows "New" |

## Incidental fix

The suite was reading provider credentials from whatever `.env` the developer
happened to have: a real `STRIPE_SECRET_KEY` swapped the deterministic card
stand-in for the live Stripe adapter and failed five payments tests. An autouse
fixture in `tests/conftest.py` now clears every third-party credential for the
duration of a test, so the suite describes its own world and matches the
"no setup needed" promise in CLAUDE.md. A test that wants a provider configured
monkeypatches it back, as the phase-F card tests already did.

## Verification

```bash
pytest                         # backend, must stay green
flake8 src                     # must stay clean
cd frontend && npm test        # vitest
cd frontend && npm run build   # tsc + vite
```

No migration: the `reviews` table already has everything needed.

## Out of scope

- Sorting or filtering restaurants by rating — that belongs with the advanced
  search in phase I.
- Owner replies to reviews.
- Editing or deleting a review once written.
- Voting a review helpful, or any moderation flow.
