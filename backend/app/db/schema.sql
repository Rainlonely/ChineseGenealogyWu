CREATE TABLE IF NOT EXISTS modern_persons (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  gender TEXT,
  birth_date TEXT,
  death_date TEXT,
  living_status TEXT,
  surname TEXT,
  is_external_surname INTEGER NOT NULL DEFAULT 0,
  education TEXT,
  occupation TEXT,
  bio TEXT,
  created_from_submission_id INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_from_submission_id) REFERENCES change_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS modern_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_person_ref TEXT NOT NULL,
  to_person_ref TEXT NOT NULL,
  from_person_source TEXT NOT NULL CHECK (from_person_source IN ('historical', 'modern')),
  to_person_source TEXT NOT NULL CHECK (to_person_source IN ('historical', 'modern')),
  relation_type TEXT NOT NULL CHECK (
    relation_type IN ('father_son', 'father_daughter', 'mother_son', 'mother_daughter', 'spouse')
  ),
  status TEXT NOT NULL DEFAULT 'active',
  created_from_submission_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (
    from_person_ref,
    to_person_ref,
    from_person_source,
    to_person_source,
    relation_type
  ),
  FOREIGN KEY (created_from_submission_id) REFERENCES change_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS lineage_attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  historical_person_ref TEXT NOT NULL,
  modern_person_ref TEXT NOT NULL,
  created_from_submission_id INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (historical_person_ref, modern_person_ref),
  FOREIGN KEY (created_from_submission_id) REFERENCES change_submissions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS change_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_person_ref TEXT NOT NULL,
  target_person_source TEXT NOT NULL CHECK (target_person_source IN ('historical', 'modern')),
  submission_type TEXT NOT NULL CHECK (
    submission_type IN ('add_person', 'add_relation', 'add_person_with_relation')
  ),
  submitter_name TEXT NOT NULL,
  submitter_contact TEXT,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  review_note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_modern_persons_display_name
  ON modern_persons(display_name);

CREATE INDEX IF NOT EXISTS idx_modern_relationships_from
  ON modern_relationships(from_person_source, from_person_ref, relation_type);

CREATE INDEX IF NOT EXISTS idx_modern_relationships_to
  ON modern_relationships(to_person_source, to_person_ref, relation_type);

CREATE INDEX IF NOT EXISTS idx_lineage_attachments_historical
  ON lineage_attachments(historical_person_ref, status);

CREATE INDEX IF NOT EXISTS idx_change_submissions_status
  ON change_submissions(status, created_at);
