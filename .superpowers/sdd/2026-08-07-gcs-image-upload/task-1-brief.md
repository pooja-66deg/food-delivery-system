# Task 1: Add google-cloud-storage Dependency

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `google-cloud-storage>=2.10.0` available in the Python environment

**Steps:**

- [ ] **Step 1: Add dependency to pyproject.toml**

Open `pyproject.toml` and find the `dependencies` list. Add `google-cloud-storage>=2.10.0` in alphabetical order (should go after `google-auth` if present, or in the general alphabetical sequence).

Current state (partial):
```toml
dependencies = [
    "fastapi>=0.104",
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    # ... add here
]
```

After adding:
```toml
dependencies = [
    "fastapi>=0.104",
    "google-cloud-storage>=2.10.0",
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    # ...
]
```

- [ ] **Step 2: Run uv lock to update lock file**

```bash
cd d:\Food\food-delivery-system
uv lock
```

Expected: `uv.lock` is updated with `google-cloud-storage` and its transitive dependencies.

- [ ] **Step 3: Verify import works**

```bash
python -c "from google.cloud import storage; print(storage.__version__)"
```

Expected: Version number prints without error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add google-cloud-storage dependency"
```
