# vnstock build dependency audit (#134)

Date: 2026-11-18. Read-only: no dependency was changed in the repo.

Reachability update (same day, 11:26 +07): `https://vnstocks.com` answered
HTTP 200, a wheel URL from `uv.lock` answered HEAD 200 anonymously, and
`uv lock --check` resolved cleanly — so the mirror step (option 1) is now
executable; it stayed out of this change because the mirror location is the
owner's decision. The structural finding is unchanged: the three packages
exist only on the vendor index, not on PyPI (`pypi.org/pypi/vnstock` → 404).

vnstock generation note (per the owner's request to re-check): installed
`vnstock 6.0.0` is the **official-Open-API generation** — its own summary reads
“kết nối Open API chính thức bằng khoá của bạn, chuẩn hoá kết quả thành bảng dữ
liệu thống nhất” (your key, normalized tables). The index also serves
`vnstock 6.0.1` and `vnstock-oapi 0.1.2` (lock pins 6.0.0 / 0.1.1, uploaded
2026-11-10). Bumping the lock to 6.0.1 is a separate decision: generation 6
changed tables and scales (prices in thousand-đ, units per table), so a parity
check (`#100`-style matrix) must run before any lock upgrade.

## What the build still depends on

`pyproject.toml` pins three packages to the vendor index
(`[tool.uv.sources]`, all `index = "vnstocks"` → `https://vnstocks.com/api/packages`):

| package | version | wheel files in `uv.lock` | source |
|---|---|---|---|
| `vnstock` | 6.0.0 | 5 (macOS x86_64/arm64, manylinux x86_64/aarch64, win_amd64) | vnstocks.com |
| `vnstock-oapi` | 0.1.1 | 1 (pure Python) | vnstocks.com |
| `vnstock-quant` | 1.0.0 | 5 (same platform matrix) | vnstocks.com |

`uv sync --frozen` therefore needs that host for any install — including builds
that never import vnstock. When it is down or blocks the builder, Docker,
Render and CI all fail before any test runs.

## What the installed metadata says

Checked against the installed distributions (`importlib.metadata.requires`):

- `vnstock 6.0.0` requires `vnstock-oapi`, `pandas`, `tzdata` (Windows only).
  It does **not** require `vnstock-quant`.
- `vnstock-quant 1.0.0` requires `vnstock`, `vnstock-oapi`, `numpy`, `pandas`.
- `vnstock-oapi 0.1.1` is pure Python and needs `httpx`, `certifi`,
  `keyring`, `platformdirs`, `truststore`.

## Is `vnstock-quant` still needed by this repo?

No code path imports it:

```
$ grep -rn --include=*.py 'import vnstock_quant\|from vnstock_quant' src tests scripts
(no matches)
```

- `vnstock_quant.fa` was replaced by Vietstock ratios (`providers/vs_ratios.py`,
  #81/#82/#128) and the table is explicitly gone (`financial_contracts.py`).
- `vnstock_release.py` only mentions the package in prose; it reads
  `vnstock.status()` and package metadata, never imports `vnstock_quant`.
- `tests/conftest.py` keeps a stand-in module so the suite collects without the
  private index (#100). That stub is the only remaining reason the name appears
  at all — it does not prove a runtime need.

So `vnstock-quant` is a direct dependency with no consumer in this repo. Dropping
it is a lock change, not a code change, and must not be bundled with the mirror
decision.

## Options

### 1. Mirror the wheels (keeps the lock hashes)

The lock records the exact files and SHA-256 hashes, so a mirror only changes
*where* the files are fetched from:

1. Download the 11 wheel files listed above from `vnstocks.com` once (on a
   network that can reach it).
2. Publish them as GitHub release assets (or an internal index directory).
3. Point uv at the mirror:
   - directory of files: `[tool.uv] find-links = ["..."]`, or
   - your own index: replace the `vnstocks` index URL and keep the same names.
4. `uv lock --check` must pass unchanged: the hashes in `uv.lock` still match.

Risk: the mirror becomes the supply chain. Store the files next to their
published SHA-256 (already in `uv.lock`) and keep the vendor URL in the release
notes so the copy can be re-verified.

### 2. Make vnstock an optional extra

Move the three packages to `[project.optional-dependencies]` and have the
vnstock-backed tools report `not_configured` when the extra is absent. The test
suite already collects with stand-ins (`OT_TEST_VNSTOCK_STUBS=1`), so CI can run
the non-vnstock part without the vendor index.

Cost: a real surface change — every vnstock-backed tool needs the “extra not
installed” branch, and production installs must remember `.[vnstock]`.

### 3. Drop `vnstock-quant` only

Independent of 1 and 2: remove the pin, run `uv lock`, and delete the conftest
stub once the suite collects without it. Cuts 5 of the 11 wheel files and the
largest native artifact.

## Recommendation

1. Mirror the three packages (option 1) — smallest change, lock untouched, fixes
   the build failure that affects every deployment.
2. Drop `vnstock-quant` in a separate PR (option 3), after confirming on a clean
   environment that `import vnstock` and the suite both work without it.
3. Keep option 2 in reserve; it is a product decision about what the server is
   without vnstock, not a packaging one.

## What was deliberately not done here

- No wheel was mirrored and no lock file changed: the mirror location and
  hosting are the owner's decision (#134), and lock upgrades (6.0.0 → 6.0.1,
  `vnstock-quant` removal) each need their own parity check and PR.
- The index version listing is anonymous-readable (`/api/packages/vnstock`,
  PEP 503), so the mirror download in option 1 step 1 can run from this
  network today.
