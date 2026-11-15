CREATE TABLE words (
 id TEXT PRIMARY KEY, deck TEXT NOT NULL CHECK(deck IN ('job','ielts','business')),
 term TEXT NOT NULL, pos TEXT NOT NULL, meaning TEXT NOT NULL,
 collocation TEXT NOT NULL, example TEXT NOT NULL, translation TEXT NOT NULL,
 source_url TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE scenarios (id TEXT PRIMARY KEY,q TEXT NOT NULL,hint TEXT NOT NULL,answer TEXT NOT NULL);
CREATE TABLE reviews (word_id TEXT PRIMARY KEY REFERENCES words(id),stage INTEGER NOT NULL CHECK(stage BETWEEN 0 AND 5),due INTEGER NOT NULL,count INTEGER NOT NULL);
CREATE TABLE daily_words (day TEXT NOT NULL,word_id TEXT NOT NULL REFERENCES words(id),PRIMARY KEY(day,word_id));
CREATE TABLE review_events (request_id TEXT PRIMARY KEY,word_id TEXT NOT NULL REFERENCES words(id),rating TEXT NOT NULL,created_at INTEGER NOT NULL,local_day TEXT NOT NULL);
CREATE TABLE drafts (scenario_id TEXT PRIMARY KEY REFERENCES scenarios(id),text TEXT NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE quiz_attempts (request_id TEXT PRIMARY KEY,word_id TEXT NOT NULL REFERENCES words(id),answer TEXT NOT NULL,correct INTEGER NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE videos (
 youtube_id TEXT PRIMARY KEY,title TEXT NOT NULL,channel TEXT NOT NULL,channel_url TEXT NOT NULL,
 thumbnail_url TEXT NOT NULL,deck TEXT NOT NULL CHECK(deck IN ('job','ielts','business')),
 source TEXT NOT NULL,source_query TEXT NOT NULL DEFAULT '',learning_hint TEXT NOT NULL DEFAULT '',
 fetched_at INTEGER NOT NULL,published_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE video_progress (
 youtube_id TEXT PRIMARY KEY REFERENCES videos(youtube_id),notes TEXT NOT NULL DEFAULT '',
 favorite INTEGER NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL
);
CREATE TABLE sync_runs (
 id TEXT PRIMARY KEY,status TEXT NOT NULL,started_at INTEGER NOT NULL,finished_at INTEGER,
 imported INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,details TEXT NOT NULL DEFAULT '[]',mode TEXT NOT NULL
);
CREATE INDEX reviews_due ON reviews(due);
CREATE INDEX videos_deck ON videos(deck);
CREATE INDEX review_events_date ON review_events(created_at);
