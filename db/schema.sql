PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  label TEXT,
  page_start INTEGER,
  page_end INTEGER,
  source_pdf TEXT,
  raw_images_dir TEXT,
  cropped_images_dir TEXT,
  notes_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  page_no INTEGER NOT NULL,
  image_path TEXT,
  generation_hint_json TEXT NOT NULL DEFAULT '[]',
  text_items_json TEXT NOT NULL DEFAULT '[]',
  line_items_json TEXT NOT NULL DEFAULT '[]',
  raw_markers_json TEXT NOT NULL DEFAULT '[]',
  manual_notes_json TEXT NOT NULL DEFAULT '[]',
  people_locked INTEGER NOT NULL DEFAULT 0,
  page_role TEXT,
  keep_generation_axis INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (group_id, page_no)
);

CREATE TABLE IF NOT EXISTS persons (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  canonical_name TEXT,
  generation INTEGER NOT NULL,
  root_order INTEGER,
  primary_page_no INTEGER,
  primary_page_image_path TEXT,
  bbox_json TEXT,
  poly_json TEXT,
  glyph_asset_path TEXT,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  notes_json TEXT NOT NULL DEFAULT '[]',
  is_verified INTEGER NOT NULL DEFAULT 0,
  verified_at TEXT,
  review_status TEXT NOT NULL DEFAULT 'draft',
  remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (group_id, primary_page_no) REFERENCES pages(group_id, page_no) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope TEXT NOT NULL,
  scope_ref TEXT NOT NULL,
  parent_person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  child_person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL DEFAULT 'father_child',
  birth_order_under_parent INTEGER,
  confidence REAL,
  page_sources_json TEXT NOT NULL DEFAULT '[]',
  notes_json TEXT NOT NULL DEFAULT '[]',
  is_verified INTEGER NOT NULL DEFAULT 0,
  verified_at TEXT,
  remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (parent_person_id <> child_person_id),
  UNIQUE (scope, scope_ref, parent_person_id, child_person_id, relation_type)
);

CREATE TABLE IF NOT EXISTS biography_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  page_no INTEGER NOT NULL,
  image_path TEXT NOT NULL,
  source_pdf TEXT,
  ocr_json_path TEXT,
  review_status TEXT NOT NULL DEFAULT 'draft',
  manual_notes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (project_id, page_no)
);

CREATE TABLE IF NOT EXISTS person_biographies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  source_page_no INTEGER NOT NULL,
  source_image_path TEXT,
  source_title_text TEXT,
  source_columns_json TEXT NOT NULL DEFAULT '[]',
  source_text_raw TEXT,
  source_text_linear TEXT,
  source_text_punctuated TEXT,
  source_text_baihua TEXT,
  source_text_translation_notes TEXT,
  match_status TEXT NOT NULL DEFAULT 'pending',
  match_confidence REAL,
  notes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id, source_page_no) REFERENCES biography_pages(project_id, page_no) ON DELETE CASCADE,
  UNIQUE (person_id, project_id, source_page_no)
);

CREATE INDEX IF NOT EXISTS idx_pages_group_page_no ON pages(group_id, page_no);
CREATE INDEX IF NOT EXISTS idx_persons_group_generation ON persons(group_id, generation);
CREATE INDEX IF NOT EXISTS idx_persons_primary_page ON persons(group_id, primary_page_no);
CREATE INDEX IF NOT EXISTS idx_relationships_parent ON relationships(parent_person_id, birth_order_under_parent);
CREATE INDEX IF NOT EXISTS idx_relationships_child ON relationships(child_person_id);
CREATE INDEX IF NOT EXISTS idx_relationships_scope ON relationships(scope, scope_ref);
CREATE INDEX IF NOT EXISTS idx_biography_pages_project_page_no ON biography_pages(project_id, page_no);
CREATE INDEX IF NOT EXISTS idx_person_biographies_person_id ON person_biographies(person_id);
CREATE INDEX IF NOT EXISTS idx_person_biographies_project_page_no ON person_biographies(project_id, source_page_no);

CREATE VIEW IF NOT EXISTS v_person_child_stats AS
SELECT
  p.id AS person_id,
  COUNT(r.child_person_id) AS child_count
FROM persons AS p
LEFT JOIN relationships AS r
  ON r.parent_person_id = p.id
GROUP BY p.id;

CREATE VIEW IF NOT EXISTS v_person_children_json AS
SELECT
  p.id AS person_id,
  COALESCE(
    json_group_array(r.child_person_id) FILTER (WHERE r.child_person_id IS NOT NULL),
    '[]'
  ) AS child_ids_json
FROM persons AS p
LEFT JOIN relationships AS r
  ON r.parent_person_id = p.id
GROUP BY p.id;

CREATE VIEW IF NOT EXISTS v_person_parent_links AS
SELECT
  p.id AS person_id,
  SUM(CASE WHEN r.scope = 'group_internal' THEN 1 ELSE 0 END) AS internal_parent_links,
  SUM(CASE WHEN r.scope = 'group_bridge' THEN 1 ELSE 0 END) AS bridge_parent_links,
  COUNT(r.id) AS total_parent_links
FROM persons AS p
LEFT JOIN relationships AS r
  ON r.child_person_id = p.id
GROUP BY p.id;

CREATE VIEW IF NOT EXISTS v_person_tree_status AS
SELECT
  p.id AS person_id,
  p.group_id,
  p.generation,
  CASE
    WHEN p.is_verified = 1 THEN 'verified'
    WHEN COALESCE(parent_links.bridge_parent_links, 0) > 0 THEN 'linked_cross_group'
    WHEN COALESCE(parent_links.internal_parent_links, 0) > 0 THEN 'linked_inside_group'
    ELSE 'isolated'
  END AS tree_status,
  COALESCE(parent_links.internal_parent_links, 0) AS internal_parent_links,
  COALESCE(parent_links.bridge_parent_links, 0) AS bridge_parent_links,
  COALESCE(parent_links.total_parent_links, 0) AS total_parent_links,
  COALESCE(child_stats.child_count, 0) AS child_count
FROM persons AS p
LEFT JOIN v_person_parent_links AS parent_links
  ON parent_links.person_id = p.id
LEFT JOIN v_person_child_stats AS child_stats
  ON child_stats.person_id = p.id;

CREATE VIEW IF NOT EXISTS v_group_completion AS
WITH min_generation AS (
  SELECT group_id, MIN(generation) AS min_generation
  FROM persons
  GROUP BY group_id
)
SELECT
  p.group_id,
  COUNT(*) FILTER (
    WHERE p.generation > mg.min_generation
      AND COALESCE(status.total_parent_links, 0) = 0
  ) AS missing_parent_count,
  COUNT(*) FILTER (
    WHERE p.generation > mg.min_generation
      AND COALESCE(status.bridge_parent_links, 0) > 0
  ) AS cross_group_linked_count,
  COUNT(*) FILTER (
    WHERE p.generation > mg.min_generation
  ) AS non_root_person_count
FROM persons AS p
JOIN min_generation AS mg
  ON mg.group_id = p.group_id
LEFT JOIN v_person_tree_status AS status
  ON status.person_id = p.id
GROUP BY p.group_id;
