ALTER TABLE words ADD COLUMN example_kind TEXT NOT NULL DEFAULT 'example' CHECK(example_kind IN ('example','definition'));
ALTER TABLE words ADD COLUMN source_label TEXT NOT NULL DEFAULT '';
CREATE INDEX words_deck_active ON words(deck,archived);
CREATE INDEX videos_deck_fetched ON videos(deck,fetched_at);
