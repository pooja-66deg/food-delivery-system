# Task 2: Add GCS Configuration

**Files:**
- Modify: `src/config.py`

**Interfaces:**
- Produces: 
  - `settings.gcs_bucket_name: Optional[str]` (loaded from `GCS_BUCKET_NAME` env var)
  - Default is `None`; required in production, ignored in development

**Steps:**

- [ ] **Step 1: Add gcs_bucket_name field to Settings class**

Open `src/config.py` and locate the `Settings` class. Find the line `media_root: str = "media"` (around line 58). Add the GCS setting right after it:

```python
# Media (uploaded images)
media_root: str = "media"

# Google Cloud Storage (production only)
gcs_bucket_name: Optional[str] = None
```

- [ ] **Step 2: Verify config loads from environment**

Create a temporary test file `test_config_gcs.py`:

```python
import os
os.environ["GCS_BUCKET_NAME"] = "test-bucket"
from src.config import settings
assert settings.gcs_bucket_name == "test-bucket"
print("✓ Config loads GCS_BUCKET_NAME correctly")
```

Run it:
```bash
python test_config_gcs.py
```

Expected: "✓ Config loads GCS_BUCKET_NAME correctly" prints.

- [ ] **Step 3: Clean up test file**

```bash
rm test_config_gcs.py
```

- [ ] **Step 4: Commit**

```bash
git add src/config.py
git commit -m "feat: add gcs_bucket_name configuration"
```
