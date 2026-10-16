# Graph Report - mercadona-scraper  (2026-10-16)

## Corpus Check
- 113 files · ~70,789 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 4, .example 1, .lock 1)

## Summary
- 895 nodes · 2312 edges · 40 communities (20 shown, 20 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 304 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Cache Repositories & Response Schemas
- Mercadona Algolia Client
- Logging & Request ID
- Settings & API Key Auth
- Domain Errors & Warehouse Resolver
- Specs 005-011 Design Concepts
- Constitution & Project Conventions
- Upstream Error & Auth Tests
- Integration Test Fixtures
- App Lifespan & Health Tests
- Algolia Raw Models & Mapper
- Products Endpoint & Dependencies
- Query Validation & Normalization
- Warehouse Resolution Tests
- Products Route Tests
- Unresponsive Redis Tests
- Search Completeness Tests
- Products Error Route Tests
- Upstream Schema Mutations
- Happy Path Integration
- Smoke Tests
- Auth Short-Circuit Tests
- Empty Search Test
- Scaffolding Test
- Test Client Fixture
- Fake Redis Factory
- Persistent 429 Test
- Fast Retry Fixture A
- Fast Retry Fixture B
- Broken Redis Factory
- Project Root

## God Nodes (most connected - your core abstractions)
1. `MercadonaClient` - 99 edges
2. `Settings` - 98 edges
3. `CacheRepository` - 64 edges
4. `WarehouseCacheRepository` - 48 edges
5. `algolia_response()` - 34 edges
6. `mock_change_pc()` - 29 edges
7. `search_products()` - 28 edges
8. `ProductQuery` - 23 edges
9. `verify_api_key()` - 20 edges
10. `resolve_warehouse()` - 19 edges

## Surprising Connections (you probably didn't know these)
- `test_empty_page_beyond_the_first_raises_page_out_of_range_without_caching()` --uses--> `PageOutOfRangeError`  [INFERRED]
  tests/services/test_product_search.py → app/exceptions.py
- `search_result()` --uses--> `RawAlgoliaProduct`  [INFERRED]
  tests/fixtures/algolia.py → app/models/mercadona_raw.py
- `_raw_algolia_product()` --uses--> `RawAlgoliaProduct`  [INFERRED]
  tests/services/test_product_search.py → app/models/mercadona_raw.py
- `test_cache_miss_resolves_via_client_and_writes_positive_cache()` --uses--> `MercadonaClient`  [INFERRED]
  tests/services/test_warehouse_resolver.py → app/scrapers/mercadona_client.py
- `test_client_returns_none_raises_not_served_and_writes_negative_cache()` --uses--> `MercadonaClient`  [INFERRED]
  tests/services/test_warehouse_resolver.py → app/scrapers/mercadona_client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Product search flow: endpoint -> service -> cache/scraper -> mapper** — specs_001_mercadona_scraper_mvp_spec_products_endpoint, specs_001_mercadona_scraper_mvp_plan_product_search_service, specs_001_mercadona_scraper_mvp_plan_cacherepository, specs_001_mercadona_scraper_mvp_plan_mercadonaclient, specs_001_mercadona_scraper_mvp_plan_product_mapper [EXTRACTED 1.00]
- **Redis graceful degradation with bounded timeouts** — specs_010_mercadona_scraper_operational_robustness_plan_cacherepository, specs_007_mercadona_scraper_warehouse_resolution_plan_warehouse_cache_repository, specs_010_mercadona_scraper_operational_robustness_plan_redis_timeout_seconds, specs_010_mercadona_scraper_operational_robustness_plan_ready_endpoint [EXTRACTED 1.00]
- **Reproducible build and verification pipeline** — specs_009_mercadona_scraper_continuous_integration_plan_uv_lockfile, specs_009_mercadona_scraper_continuous_integration_plan_github_actions_ci, specs_009_mercadona_scraper_continuous_integration_plan_docker_uv_export, specs_005_mercadona_scraper_dockerization_plan_dockerfile_multi_stage, specs_009_mercadona_scraper_continuous_integration_plan_python_version_file [EXTRACTED 1.00]
- **Upstream retry policy across specs 001-002** — specs_001_mercadona_scraper_mvp_plan_handrolled_retry_backoff, specs_001_mercadona_scraper_mvp_plan_no_retry_4xx, specs_002_mercadona_scraper_antibaneo_plan_retry_after_429, specs_002_mercadona_scraper_antibaneo_tasks_retry_jitter [EXTRACTED 1.00]
- **SDD spec -> plan -> tasks documents** — readme_spec_driven_development, specs_001_mercadona_scraper_mvp_spec_spec_001, specs_002_mercadona_scraper_antibaneo_spec_spec_002, specs_003_mercadona_scaper_logging_spec_spec_003, specs_004_mercadona_scraper_authentication_spec_spec_004 [INFERRED 0.85]
- **Upstream failures mapped to 502 Bad Gateway** — specs_007_mercadona_scraper_warehouse_resolution_plan_upstreamunavailableerror, specs_007_mercadona_scraper_warehouse_resolution_spec_warehouse_header_missing, specs_011_mercadona_scraper_upstream_schema_resilience_plan_algoliaresponseinvalid, specs_011_mercadona_scraper_upstream_schema_resilience_plan_rawalgoliaresponse [INFERRED 0.85]

## Communities (40 total, 20 thin omitted)

### Community 0 - "Cache Repositories & Response Schemas"
Cohesion: 0.05
Nodes (42): AppState, ProductOut, ProductSearchResponse, SearchMeta, CacheRepository, search_products(), test_app_state_exposes_the_four_fields_as_given(), search_result() (+34 more)

### Community 1 - "Mercadona Algolia Client"
Cohesion: 0.06
Nodes (36): AlgoliaCredentialsUnavailable, _describe_validation_error(), _error_for_response(), MercadonaClient, _parse_retry_after(), WarehouseHeaderMissing, _algolia_response_with_one_hit(), settings() (+28 more)

### Community 2 - "Logging & Request ID"
Cohesion: 0.05
Nodes (22): bind_request_id(), configure_logging(), _RequestIdFilter, health(), lifespan(), ready(), unhandled_exception_handler(), RequestLoggingMiddleware (+14 more)

### Community 3 - "Settings & API Key Auth"
Cohesion: 0.07
Nodes (33): Settings, verify_api_key(), required_env(), test_api_keys_defaults_to_empty(), test_api_keys_ignores_empty_entries(), test_api_keys_parses_comma_separated_values(), test_api_keys_strips_whitespace_around_commas(), test_non_positive_timeouts_are_rejected() (+25 more)

### Community 4 - "Domain Errors & Warehouse Resolver"
Cohesion: 0.08
Nodes (33): PageOutOfRangeError, PostalCodeNotServedError, UpstreamUnavailableError, CachedWarehouse, WarehouseCacheRepository, resolve_warehouse(), Plan 007 - Warehouse Resolution, PostalCodeNotServedError (-> 404) (+25 more)

### Community 5 - "Specs 005-011 Design Concepts"
Cohesion: 0.06
Nodes (56): Plan 005 - Dockerization, docker-compose.yml (api + redis:7-alpine), Multi-stage Dockerfile (python:3.11-slim, non-root appuser), Spec 005 - Dockerization, GET /health liveness endpoint, Settings (pydantic-settings env configuration), Tasks 005 - Dockerization, Plan 006 - Architecture Refactor (+48 more)

### Community 6 - "Constitution & Project Conventions"
Cohesion: 0.05
Nodes (37): Skill Registry (gentle-ai), CI Workflow (lint, format, tests via uv), AGENTS.md conventions, CLAUDE.md project guide, docker-compose API + Redis stack, Project Constitution, Mercadona Scraper API (README), Spec-Driven Development (SDD) (+29 more)

### Community 7 - "Upstream Error & Auth Tests"
Cohesion: 0.12
Nodes (20): AlgoliaResponseInvalid, _algolia_response_with_one_hit(), _mock_credentials(), _search_with_algolia_body(), settings(), test_concurrent_first_searches_fetch_credentials_once(), test_invalid_response_log_is_capped_at_five_errors(), test_search_fails_loudly_without_algolia_totals() (+12 more)

### Community 8 - "Integration Test Fixtures"
Cohesion: 0.10
Nodes (10): algolia_response(), mock_change_pc(), test_second_distinct_search_reuses_credentials_across_requests(), test_request_leaves_start_and_end_logs_with_matching_request_id(), test_persistent_5xx_returns_502_after_exhausting_retries(), test_recovers_on_third_attempt_returns_200(), test_second_identical_request_served_from_cache(), test_429_with_short_retry_after_is_absorbed() (+2 more)

### Community 9 - "App Lifespan & Health Tests"
Cohesion: 0.06
Nodes (18): _cache_with_ping(), required_env(), test_docs_and_openapi_stay_public_without_api_key(), test_health_returns_ok_without_api_key(), test_health_stays_200_when_redis_is_unavailable(), test_lifespan_applies_configured_redis_timeout(), test_lifespan_configures_logging(), test_lifespan_gives_redis_client_a_default_timeout() (+10 more)

### Community 10 - "Algolia Raw Models & Mapper"
Cohesion: 0.10
Nodes (22): _build_price_format(), map_raw_algolia_product_to_product_out(), RawAlgoliaCategory, RawAlgoliaProduct, RawAlgoliaResponse, RawAlgoliaSearchResult, RawPriceInstructions, _load_raw_algolia_product() (+14 more)

### Community 11 - "Products Endpoint & Dependencies"
Cohesion: 0.10
Nodes (11): get_products(), get_cache_repository(), get_mercadona_client(), get_settings(), get_warehouse_cache_repository(), _state(), _make_request(), test_get_cache_repository_returns_the_exact_object_on_app_state() (+3 more)

### Community 12 - "Query Validation & Normalization"
Cohesion: 0.12
Nodes (12): ProductQuery, test_product_query_accepts_page_size_bounds(), test_product_query_accepts_valid_5_digit_postal_codes(), test_product_query_measures_length_after_normalizing(), test_product_query_missing_postal_code_raises(), test_product_query_missing_term_raises(), test_product_query_normalizes_term(), test_product_query_pagination_defaults() (+4 more)

### Community 13 - "Warehouse Resolution Tests"
Cohesion: 0.14
Nodes (10): client_with_broken_redis(), _mock_change_pc_for(), _mock_credentials_and_algolia(), test_change_pc_response_without_header_returns_502_and_caches_nothing(), test_different_postal_codes_resolve_to_their_real_warehouse(), test_persistent_change_pc_failure_returns_502(), test_postal_code_without_service_returns_404_and_caches_the_negative_result(), test_postal_codes_sharing_a_warehouse_share_the_product_cache() (+2 more)

### Community 14 - "Products Route Tests"
Cohesion: 0.19
Nodes (11): app(), _raw_algolia_product(), _settings(), test_get_products_passes_resolved_warehouse_to_search(), test_get_products_rejects_blank_term_without_calling_mercadona(), test_get_products_rejects_invalid_postal_code_without_calling_mercadona(), test_get_products_rejects_oversized_page_without_calling_mercadona(), test_get_products_returns_200_with_empty_list_when_no_matches() (+3 more)

### Community 15 - "Unresponsive Redis Tests"
Cohesion: 0.17
Nodes (5): client_with_silent_redis(), _mock_upstream(), silent_redis_url(), test_ready_is_503_and_health_is_200_when_redis_never_answers(), test_search_completes_without_cache_when_redis_never_answers()

### Community 16 - "Search Completeness Tests"
Cohesion: 0.24
Nodes (8): _algolia_params(), _hits(), _mock_upstream(), test_blank_term_is_rejected_before_any_upstream_call(), test_equivalent_terms_share_one_cache_entry(), test_first_page_reports_the_real_total(), test_last_page_is_requested_as_algolia_page_minus_one(), test_out_of_range_page_is_404_and_never_cached()

### Community 17 - "Products Error Route Tests"
Cohesion: 0.24
Nodes (8): app(), _settings(), test_get_products_logs_error_when_upstream_unavailable(), test_get_products_returns_404_when_page_is_out_of_range(), test_get_products_returns_404_when_postal_code_not_served(), test_get_products_returns_502_when_resolution_upstream_unavailable(), test_get_products_returns_502_when_upstream_unavailable(), _warehouse_cache_miss()

### Community 18 - "Upstream Schema Mutations"
Cohesion: 0.25
Nodes (3): _mock_upstream(), test_changes_to_unused_fields_do_not_break_search(), test_missing_used_field_is_502_and_not_cached()

### Community 19 - "Happy Path Integration"
Cohesion: 0.25
Nodes (3): test_get_products_returns_exact_response_shape_with_valid_api_key(), _mock_upstream_chain(), test_get_products_returns_exact_response_shape()

## Knowledge Gaps
- **9 isolated node(s):** `mercadona-scraper`, `tests/fixtures/algolia.py algolia_response helper`, `.python-version pinned to 3.11`, `WARNING log with field loc and error type only (max 5)`, `mercadona_raw DTOs` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 313 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings & API Key Auth` to `Cache Repositories & Response Schemas`, `Mercadona Algolia Client`, `Logging & Request ID`, `Domain Errors & Warehouse Resolver`, `Upstream Error & Auth Tests`, `App Lifespan & Health Tests`, `Products Endpoint & Dependencies`, `Products Route Tests`, `Products Error Route Tests`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Are the 44 inferred relationships involving `MercadonaClient` (e.g. with `get_mercadona_client()` and `AppState`) actually correct?**
  _`MercadonaClient` has 44 INFERRED edges - model-reasoned connections that need verification._
- **What connects `mercadona-scraper`, `tests/fixtures/algolia.py algolia_response helper`, `.python-version pinned to 3.11` to the rest of the system?**
  _9 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Cache Repositories & Response Schemas` be split into smaller, more focused modules?**
  _Cohesion score 0.051893408134642355 - nodes in this community are weakly interconnected._
- **Why does `MercadonaClient` connect `Mercadona Algolia Client` to `Cache Repositories & Response Schemas`, `Logging & Request ID`, `Settings & API Key Auth`, `Domain Errors & Warehouse Resolver`, `Upstream Error & Auth Tests`, `App Lifespan & Health Tests`, `Products Endpoint & Dependencies`, `Products Route Tests`, `Products Error Route Tests`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `Settings` (e.g. with `get_settings()` and `verify_api_key()`) actually correct?**
  _`Settings` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Should `Mercadona Algolia Client` be split into smaller, more focused modules?**
  _Cohesion score 0.05964912280701754 - nodes in this community are weakly interconnected._