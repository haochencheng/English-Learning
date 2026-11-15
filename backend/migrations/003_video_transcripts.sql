CREATE TABLE video_transcripts (
 youtube_id TEXT PRIMARY KEY REFERENCES videos(youtube_id),
 status TEXT NOT NULL DEFAULT 'empty', request_id TEXT NOT NULL DEFAULT '',
 english_source TEXT NOT NULL DEFAULT '', translation_source TEXT NOT NULL DEFAULT '',
 is_generated INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
 updated_at INTEGER NOT NULL DEFAULT 0, last_attempt_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE transcript_segments (
 youtube_id TEXT NOT NULL REFERENCES videos(youtube_id), seq INTEGER NOT NULL,
 start REAL, duration REAL NOT NULL DEFAULT 0,
 english TEXT NOT NULL, chinese TEXT NOT NULL DEFAULT '',
 PRIMARY KEY (youtube_id,seq)
);
CREATE TABLE dictionary_entries (
 term TEXT PRIMARY KEY, phonetic TEXT NOT NULL DEFAULT '',
 translation TEXT NOT NULL, definition TEXT NOT NULL DEFAULT '',
 exchange TEXT NOT NULL DEFAULT ''
);
CREATE TABLE dictionary_forms (form TEXT NOT NULL, lemma TEXT NOT NULL, PRIMARY KEY(form,lemma));
CREATE TABLE dictionary_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
